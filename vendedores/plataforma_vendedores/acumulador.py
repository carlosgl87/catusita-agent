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
import json
import time
import uuid

from vendedores.plataforma_vendedores import redis as redis_mod

# Silencio que se espera antes de dar el turno por cerrado.
# OJO: no lo dejes en 3.0 por inercia. Sácalo de la distribución real de huecos
# entre mensajes de la tabla chat_messages — debería ser bimodal, y la ventana
# va en el valle entre los dos picos.
VENTANA = 3.0

# Tope desde el PRIMER fragmento. Sin esto, alguien escribiendo sin parar cada
# 2 segundos no recibiría respuesta nunca.
TOPE = 20.0

TTL = 600            # los acumuladores no viven más que esto
LOCK_TTL = 180       # margen para la corrida más lenta (SUNARP tarda hasta 60s)
MAX_MEDIA_BYTES = 8 * 1024 * 1024   # techo por archivo al descargar


def _k(multiagente: str, conv: str) -> tuple[str, str, str]:
    """El multiagente va en la clave: aunque el router fallara, el historial de un
    vendedor no podría cruzarse con una sesión de cliente."""
    base = f"{multiagente}:{conv}"
    return f"acum:{base}", f"acum:ts:{base}", f"acum:ini:{base}"


# ── Lua ───────────────────────────────────────────────────────────────────────
# En scripts para que cada operación sea atómica. Es la diferencia entre "casi
# nunca falla" y "no puede fallar".

_ACUMULAR = """
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SET', KEYS[2], ARGV[2], 'EX', tonumber(ARGV[3]))
redis.call('SET', KEYS[3], ARGV[2], 'NX', 'EX', tonumber(ARGV[3]))
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

    WAHA entrega la media como URL (`media.url`), no como base64 — por eso el
    sobre es liviano sin esfuerzo. Lo que NO se hace es guardar esa URL y
    olvidarse: ver `resolver_media`.
    """
    media = payload.get("media") or {}
    return {
        "id": payload.get("id"),
        "texto": (payload.get("body") or "").strip(),
        "media": {
            "url": media.get("url"),
            "mimetype": media.get("mimetype"),
            "filename": media.get("filename"),
        } if payload.get("hasMedia") and media.get("url") else None,
    }


async def acumular(multiagente: str, conv: str, payload: dict) -> float:
    """Agrega un fragmento y devuelve su timestamp.

    Ese timestamp es la identidad del job diferido: quien lo agende volverá con
    él y solo procesará si sigue siendo el más reciente.
    """
    r = await redis_mod.get()
    ahora = time.time()
    await r.eval(
        _ACUMULAR, 3, *_k(multiagente, conv),
        json.dumps(_sobre(payload), ensure_ascii=False), str(ahora), str(TTL),
    )
    return ahora


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

    TODO: usar shared/waha.py::_headers y WAHA_BASE_URL para las URLs relativas
    (WAHA devuelve rutas que empiezan con '/'). Ver webhooks/whatsapp.py:657.
    """
    raise NotImplementedError


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
