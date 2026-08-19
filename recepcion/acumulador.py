"""Acumulador de mensajes por conversación (debounce).

En WhatsApp la gente escribe en fragmentos:

    19:04:01  "hola"
    19:04:03  "oye una consulta"
    19:04:09  "tienes filtro de aceite para corolla 2015?"

Sin debounce eso son tres corridas del agente sobre el mismo historial, tres
respuestas y una carrera al escribir en Redis. Con debounce es un turno: se
esperan unos segundos de silencio, se unen los fragmentos y el agente corre UNA
vez, viendo la pregunta completa.

Generaliza el acumulador de `shared/yahuar.py` con cuatro diferencias:

  1. una clave por conversación y por multiagente, no una global
  2. el temporizador es un job diferido en Redis, no un `asyncio.sleep`
     -> sobrevive a un redeploy (en Railway, cada push a main es uno)
  3. el drenaje es atómico (Lua), no LRANGE + DEL
     -> desaparece la carrera que hoy se parchea con `acumulador_ya_procesado`
  4. hay un tope: si los fragmentos no paran, igual se responde

── Cómo encaja ────────────────────────────────────────────────────────────────

  webhook   ya_visto(id) -> acumular() -> encolar procesar(conv, ts) en VENTANA s
  worker    tomar_lock() -> reclamar() -> resolver_media() -> unir() -> grafo

── Por qué se guarda un "sobre" y no el payload de WAHA ───────────────────────

El acumulador guarda lo MÍNIMO para reconstruir el turno: texto y una referencia
a la media. Nunca bytes. Tres razones:

  - el drenaje es un script Lua, y Lua bloquea el event loop de Redis mientras
    serializa su respuesta. Devolver sobres son cientos de bytes; devolver
    imágenes serían megabytes con Redis congelado para todos
  - el payload crudo de WAHA trae mucho ruido del protocolo que no se usa
  - si WAHA cambia la forma del payload, solo cambia `_sobre()`

La media se resuelve al DRENAR, no al acumular (ver `resolver_media`).
"""
import asyncio
import base64
import json
import logging
import time
import uuid

import httpx

from recepcion import redis as redis_mod, waha

# Silencio que se espera antes de dar el turno por cerrado.
# OJO: no lo dejes en 3.0 por inercia. Sácalo de la distribución real de huecos
# entre mensajes de la tabla chat_messages — debería ser bimodal, y la ventana
# va en el valle entre los dos picos.
VENTANA = 3.0

# Tope desde el PRIMER fragmento. Sin esto, alguien escribiendo sin parar cada
# 2 segundos no recibiría respuesta nunca.
TOPE = 20.0

TTL = 600            # los acumuladores no viven más que esto
LOCK_TTL = 180       # margen para la corrida más lenta (la placa tarda hasta 60s)
MAX_MEDIA_BYTES = 8 * 1024 * 1024   # techo por archivo al descargar


# Índice de turnos abiertos, ordenado por CUÁNDO vencen. Una sola clave para
# todo el sistema: el drenador hace un ZRANGEBYSCORE por latido en vez de
# recorrer claves. `SCAN acum:*` sería O(claves totales) cada segundo.
PENDIENTES = "acum:pendientes"


def _k(multiagente: str, conv: str) -> tuple[str, str, str]:
    """El multiagente va en la clave: aunque el router fallara, el historial de un
    vendedor no podría cruzarse con una sesión de cliente."""
    base = f"{multiagente}:{conv}"
    return f"acum:{base}", f"acum:ts:{base}", f"acum:ini:{base}"


def _miembro(multiagente: str, conv: str) -> str:
    return f"{multiagente}|{conv}"


def _partes(miembro: str) -> tuple[str, str]:
    ma, _, conv = miembro.partition("|")
    return ma, conv


# ── Lua ───────────────────────────────────────────────────────────────────────
# En scripts para que cada operación sea atómica. Es la diferencia entre "casi
# nunca falla" y "no puede fallar".

# Guarda el fragmento y calcula CUÁNDO vence el turno:
#
#     vence = min(ahora + VENTANA,  primer_fragmento + TOPE)
#
# Las dos mitades son necesarias. La primera es el debounce: cada fragmento
# nuevo corre el vencimiento hacia adelante y el turno cierra recién cuando hay
# silencio. La segunda es el techo: sin ella, alguien escribiendo cada 2
# segundos empujaría el vencimiento para siempre y nunca recibiría respuesta.
#
# Se calcula acá y no en el drenador porque es el único lugar que ve `ini` y el
# fragmento nuevo en el mismo instante.
_ACUMULAR = """
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SET', KEYS[2], ARGV[2], 'EX', tonumber(ARGV[3]))
redis.call('SET', KEYS[3], ARGV[2], 'NX', 'EX', tonumber(ARGV[3]))
local ini = tonumber(redis.call('GET', KEYS[3]))
local vence = tonumber(ARGV[2]) + tonumber(ARGV[4])
local techo = ini + tonumber(ARGV[5])
if techo < vence then vence = techo end
redis.call('ZADD', KEYS[4], vence, ARGV[6])
return redis.call('LLEN', KEYS[1])
"""

# Cede el turno si llegó un fragmento más nuevo, SALVO que ya se haya alcanzado
# el tope. Si reclama, drena y limpia en el mismo paso atómico.
_RECLAMAR = """
local ts = redis.call('GET', KEYS[2])
if not ts then return nil end
local ini = tonumber(redis.call('GET', KEYS[3]) or ARGV[2])
local toco_techo = (tonumber(ARGV[2]) - ini) >= tonumber(ARGV[3])
if tonumber(ts) > tonumber(ARGV[1]) and not toco_techo then
  return nil
end
local items = redis.call('LRANGE', KEYS[1], 0, -1)
redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
return items
"""

# Solo suelta el lock si sigue siendo mío. Si mi corrida se pasó del TTL y otro
# worker ya tomó el turno, borrar a ciegas le quitaría el lock a él.
_SOLTAR = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def _sobre(payload: dict) -> dict:
    """Payload de WAHA -> lo mínimo para reconstruir el turno. Sin bytes.

    ── WAHA manda la media de DOS formas ──────────────────────────────────────

    Depende de cómo esté configurado el contenedor:

        media.url     una ruta para descargar, EFÍMERA
        media.data    el base64 metido en el propio webhook
                      (WHATSAPP_HOOK_MEDIA_INLINE=true — así está hoy)

    Hay que soportar las dos. Mirar solo `url` —que era la primera versión de
    esto— descartaba en silencio toda foto que mandara un usuario, porque con
    media inline el campo `url` viene vacío.

    ── Por qué el base64 no entra en el sobre ─────────────────────────────────

    El sobre viaja en la lista que drena el script Lua, y Lua bloquea el event
    loop de Redis mientras serializa su respuesta. Sobres de texto son cientos
    de bytes; una foto son megabytes con Redis congelado para todos.

    Así que los bytes se guardan aparte, en su propia clave, y el sobre lleva
    solo el nombre de esa clave. `resolver_media` la lee al cerrar el turno.
    """
    media = payload.get("media") or {}
    if not payload.get("hasMedia"):
        ref = None
    elif media.get("data"):
        ref = {"blob": _blob(payload.get("id") or ""),
               "mimetype": media.get("mimetype"), "filename": media.get("filename")}
    elif media.get("url"):
        ref = {"url": media["url"],
               "mimetype": media.get("mimetype"), "filename": media.get("filename")}
    else:
        ref = None

    return {
        "id": payload.get("id"),
        "texto": (payload.get("body") or "").strip(),
        # Sin normalizar, a propósito. `conversacion` es el número limpio, para
        # buscar en el roster; esto es la dirección de vuelta, y si el contacto
        # se presentó como LID hay que contestarle al LID.
        "responder_a": payload.get("from") or "",
        "media": ref,
    }


def _blob(mensaje_id: str) -> str:
    return f"media:{mensaje_id}"


async def acumular(multiagente: str, conv: str, payload: dict) -> float:
    """Agrega un fragmento al turno abierto y devuelve en cuántos segundos vence.

    El webhook termina acá: no espera, no procesa, contesta 200. Quien cierra el
    turno es el drenador cuando ese vencimiento pasa.
    """
    r = await redis_mod.get()
    ahora = time.time()
    claves = _k(multiagente, conv)

    # Los bytes van a su propia clave, fuera de la lista que drena el Lua.
    # Mismo TTL que el acumulador: si el turno nunca se cierra, no queda una
    # foto ocupando memoria en Redis para siempre.
    inline = ((payload.get("media") or {}).get("data") or "") if payload.get("hasMedia") else ""
    if inline:
        await r.set(_blob(payload.get("id") or ""), inline, ex=TTL)

    await r.eval(
        _ACUMULAR, 4, *claves, PENDIENTES,
        json.dumps(_sobre(payload), ensure_ascii=False), str(ahora), str(TTL),
        str(VENTANA), str(TOPE), _miembro(multiagente, conv),
    )
    return VENTANA


async def vencidos(hasta: float) -> list[tuple[str, str, float]]:
    """Turnos cuyo plazo ya pasó: [(multiagente, conversacion, vencimiento)].

    No los saca del índice. Sacarlos acá y fallar después —Redis se cae, el
    proceso se reinicia— perdería el turno sin dejar rastro. Los quita
    `cerrar()`, recién cuando el Turno ya está encolado.
    """
    r = await redis_mod.get()
    crudos = await r.zrangebyscore(PENDIENTES, "-inf", hasta, withscores=True)
    return [(*_partes(m), s) for m, s in crudos]


async def cerrar(multiagente: str, conv: str) -> None:
    """Saca el turno del índice. Se llama cuando ya se encoló."""
    r = await redis_mod.get()
    await r.zrem(PENDIENTES, _miembro(multiagente, conv))


async def posponer(multiagente: str, conv: str, segundos: float) -> None:
    """Corre el vencimiento hacia adelante sin tocar los fragmentos.

    Para cuando el turno no se pudo tomar ahora —hay una corrida en curso sobre
    esa misma conversación— y hay que reintentar. Sin esto el drenador lo
    miraría en cada latido mientras dure la corrida anterior.
    """
    r = await redis_mod.get()
    await r.zadd(PENDIENTES, {_miembro(multiagente, conv): time.time() + segundos})


async def abierto(multiagente: str, conv: str) -> bool:
    """¿Queda algo del turno en Redis?

    Sirve para distinguir los dos motivos por los que `reclamar` devuelve None:
    llegó un fragmento más nuevo (el turno sigue vivo, se reintenta) o el
    acumulador expiró por TTL (entrada huérfana en el índice, se descarta).
    """
    r = await redis_mod.get()
    return bool(await r.exists(_k(multiagente, conv)[1]))


async def reclamar(multiagente: str, conv: str, ts_mio: float) -> list[dict] | None:
    """Intenta quedarse con el turno.

    None  -> llegó un fragmento más nuevo; el job de ESE se encargará.
    lista -> el turno es tuyo, ya drenado y limpio. Nadie más lo verá.
    """
    r = await redis_mod.get()
    items = await r.eval(
        _RECLAMAR, 3, *_k(multiagente, conv), str(ts_mio), str(time.time()), str(TOPE)
    )
    if not items:
        return None
    return [json.loads(x) for x in items]


async def resolver_media(sobres: list[dict]) -> list[dict]:
    """Descarga la media AL DRENAR y la deja en `bytes_b64` de cada sobre.

    Se hace acá y no al acumular por dos razones opuestas que se equilibran:

      - al acumular sería demasiado temprano: el webhook debe responder en
        milisegundos y una descarga lo frenaría
      - al enviar sería demasiado tarde: la URL de WAHA es EFÍMERA. Si el job se
        reintenta o la cola se atrasa, el archivo ya no está

    Si la descarga falla, el sobre queda con `media_perdida=True` y el turno
    sigue. Vale más responder el texto y pedir que reenvíen la foto, que morir
    reintentando un archivo que ya no existe. NO reintentar un 404: es
    definitivo.

    Las descargas del turno van en paralelo: tres fotos son tres viajes al mismo
    host y encadenarlos triplica lo que el usuario espera sin ganar nada.

    Los que llegaron inline no se descargan: ya están en Redis, guardados por
    `acumular` fuera de la lista del Lua. Solo hay que ir a buscarlos.
    """
    guardados = [s for s in sobres if (s.get("media") or {}).get("blob")]
    remotos = [s for s in sobres if (s.get("media") or {}).get("url")]

    if guardados:
        r = await redis_mod.get()
        claves = [s["media"]["blob"] for s in guardados]
        for sobre, b64 in zip(guardados, await r.mget(claves)):
            if b64:
                sobre["media"]["bytes_b64"] = b64
            else:
                # Expiró el TTL antes de cerrar el turno. Solo pasa si el turno
                # estuvo abierto más de TTL, que no debería.
                logging.warning(f"[media] blob vencido: {sobre['media']['blob']}")
                sobre["media_perdida"] = True
        # Los bytes ya están en el sobre; dejarlos también en Redis duplicaría
        # megabytes hasta que venza el TTL.
        await r.delete(*claves)

    if remotos:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cli:
            await asyncio.gather(*(_bajar(cli, s) for s in remotos))

    return sobres


async def _bajar(cli: httpx.AsyncClient, sobre: dict) -> None:
    """Descarga la media de UN sobre. Nunca lanza: marca y sigue."""
    media = sobre["media"]
    url = waha.url_de(media["url"])
    try:
        r = await cli.get(url, headers=waha.headers())
        if r.status_code >= 400:
            # Un 404 acá es la URL efímera que ya caducó. Reintentar no la trae.
            raise RuntimeError(f"HTTP {r.status_code}")

        if len(r.content) > MAX_MEDIA_BYTES:
            # Se corta antes de codificar: base64 crece un tercio, y el sobre
            # entero viaja por Redis y después por la API de Anthropic.
            raise RuntimeError(f"{len(r.content)} bytes, tope {MAX_MEDIA_BYTES}")

        media["bytes_b64"] = base64.b64encode(r.content).decode()
        media["mimetype"] = media.get("mimetype") or r.headers.get("content-type", "")
    except Exception as e:
        logging.warning(f"[media] no se pudo bajar {url}: {e}")
        sobre["media_perdida"] = True


async def tomar_lock(multiagente: str, conv: str) -> str | None:
    """Lock de conversación. Devuelve el token, o None si ya hay una corrida.

    Se toma ANTES de reclamar. Si se reclamara primero y después fallara el
    lock, los fragmentos ya drenados se perderían.

    Existe porque el debounce no alcanza: si el agente tarda 8s y el usuario
    escribe a los 5, el segundo turno arrancaría encima del primero.
    """
    r = await redis_mod.get()
    token = uuid.uuid4().hex
    if await r.set(f"lock:{multiagente}:{conv}", token, nx=True, ex=LOCK_TTL):
        return token
    return None


async def soltar_lock(multiagente: str, conv: str, token: str) -> None:
    r = await redis_mod.get()
    await r.eval(_SOLTAR, 1, f"lock:{multiagente}:{conv}", token)


async def ya_visto(mensaje_id: str, ttl: int = 600) -> bool:
    """Idempotencia por ID de mensaje de WAHA.

    Esto es lo que hoy falta en `/webhook/waha`: el `X-Idempotency-Key` solo
    existe en el handler de Kapso, que no está en uso (WHATSAPP_PROVIDER=waha).

    OJO — marca "visto", no "respondido". Se llama al RECIBIR, para no encolar
    dos veces el mismo mensaje. Lo que evita responder dos veces es el lock más
    el reclamo atómico, no esta función.
    """
    if not mensaje_id:
        return False
    r = await redis_mod.get()
    return not await r.set(f"visto:{mensaje_id}", "1", ex=ttl, nx=True)


def unir(sobres: list[dict]) -> tuple[str, list[dict]]:
    """Convierte los sobres en UN turno del usuario.

    Devuelve (texto unido, media resuelta). El texto unido es lo que ve el
    agente y lo que se guarda en el historial: así la conversación se lee como
    un mensaje y no como tres, que además es lo que le conviene al modelo.
    """
    textos, media = [], []
    for s in sobres:
        if s.get("texto"):
            textos.append(s["texto"])
        m = s.get("media")
        if m and m.get("bytes_b64"):
            media.append(m)
        elif m and s.get("media_perdida"):
            textos.append("[el usuario mandó una imagen que ya no se pudo descargar]")
    return "\n".join(textos), media
