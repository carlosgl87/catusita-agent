"""Servicio de recepción. Lo único que mira a internet.

    uvicorn recepcion.main:app

Cuatro trabajos y ninguno más:

    1. recibir de WAHA y validar que sea WAHA
    2. decidir a qué multiagente va cada mensaje
    3. juntar los fragmentos y encolar el turno
    4. mandar por WhatsApp lo que el worker contestó

No corre agentes, no toca Postgres y no sabe qué es un SKU. Si mañana cambia el
canal de WhatsApp, solo cambia este servicio.

── El drenador ────────────────────────────────────────────────────────────────

El webhook acumula; un loop aparte drena. Están separados porque el webhook
tiene que contestar en milisegundos y el drenaje espera segundos de silencio
antes de cerrar un turno.

── Las respuestas ─────────────────────────────────────────────────────────────

Los workers dejan lo que contestaron en `respuestas:<multiagente>`. Otro loop
las saca y las manda por WhatsApp. Así el worker no necesita hablar con WAHA —
no sabe que WhatsApp existe.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from recepcion import acumulador, numeros, padron, redis as redis_mod, waha, webhook
from recepcion.contrato import Turno, VersionIncompatible, desempacar, empacar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MULTIAGENTES = ("vendedores", "clientes", "supervisores")

# Cada cuánto el drenador revisa si hay turnos listos.
LATIDO = 1.0

# Cuánto se pospone un turno que no se pudo tomar porque hay una corrida en
# curso sobre esa conversación. Reintentar cada latido sería un loop caliente
# durante los segundos que tarda el agente.
REINTENTO = 3.0

# El BRPOP se despierta cada tanto para poder atender un apagado. No es polling.
BLOQUEO = 5

COLAS_RESPUESTA = [f"respuestas:{ma}" for ma in MULTIAGENTES]


async def _drenar() -> None:
    """Cierra los turnos que cumplieron su plazo y los encola.

    El webhook solo acumula. Este loop es el que decide que un turno terminó:
    mira el índice de vencimientos, y por cada uno que ya pasó intenta cerrarlo.

    ── El orden importa ───────────────────────────────────────────────────────

        lock -> reclamar -> encolar -> cerrar

    Primero el lock: si se reclamara antes y el lock fallara, los fragmentos ya
    salieron de Redis y no hay dónde devolverlos. Y `cerrar()` recién al final,
    porque sacar del índice antes de encolar deja el turno sin dueño si algo
    revienta en el medio.

    ── Por qué no se suelta el lock acá ───────────────────────────────────────

    Porque la corrida todavía no empezó: el turno recién se encoló. El lock
    tiene que durar hasta que el worker termine, y hoy lo libera su TTL
    (LOCK_TTL). Cuando el worker devuelva el Resultado, `_enviar_respuestas` es
    el que corresponde que lo suelte.
    """
    while True:
        await asyncio.sleep(LATIDO)
        try:
            for multiagente, conv, _ in await acumulador.vencidos(time.time()):
                await _cerrar_turno(multiagente, conv)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Un error acá no puede matar el loop: sin drenador, el webhook
            # sigue aceptando mensajes y nadie los procesa nunca.
            logging.exception(f"[drenar] latido falló: {e}")


async def _cerrar_turno(multiagente: str, conv: str) -> None:
    token = await acumulador.tomar_lock(multiagente, conv)
    if token is None:
        await acumulador.posponer(multiagente, conv, REINTENTO)
        return

    sobres = await acumulador.reclamar(multiagente, conv, time.time())
    if sobres is None:
        # O llegó un fragmento más nuevo —el turno sigue abierto y su propio
        # vencimiento lo va a traer de vuelta— o el acumulador expiró y esta
        # entrada del índice quedó huérfana.
        await acumulador.soltar_lock(multiagente, conv, token)
        if not await acumulador.abierto(multiagente, conv):
            await acumulador.cerrar(multiagente, conv)
        return

    sobres = await acumulador.resolver_media(sobres)
    texto, media = acumulador.unir(sobres)
    responder_a = next(
        (s["responder_a"] for s in reversed(sobres) if s.get("responder_a")), conv
    )

    turno = Turno(
        conversacion=conv,
        multiagente=multiagente,
        texto=texto,
        # Vacío a propósito: la recepción no lee ninguna tabla y no sabe qué es
        # un `vendedor_id`. Quién es este número lo resuelve el worker contra su
        # propio roster (ver plataforma_*/worker.py::_perfil).
        perfil={},
        media=media,
        responder_a=responder_a,
        # Viaja con el turno y vuelve en el Resultado. La conversación queda
        # tomada hasta que la respuesta esté en el chat.
        lock=token,
    )

    r = await redis_mod.get()
    await r.lpush(multiagente, empacar(turno))
    await acumulador.cerrar(multiagente, conv)
    logging.info(
        f"[drenar] {conv} -> cola {multiagente} · {len(sobres)} fragmento(s)"
        f"{f' · {len(media)} adjunto(s)' if media else ''}"
    )


async def _enviar_respuestas() -> None:
    """Saca lo que contestaron los workers y lo manda por WhatsApp.

    Un BRPOP sobre las tres colas a la vez. Redis atiende la primera que tenga
    algo, así que un worker lento no le tapa la salida a los otros dos.

    Es el único punto del sistema que le habla a WAHA. Los workers no saben que
    WhatsApp existe: dejan un Resultado y siguen.
    """
    r = await redis_mod.get()
    while True:
        try:
            item = await r.brpop(COLAS_RESPUESTA, timeout=BLOQUEO)
            if item is None:
                continue
            cola, crudo = item
            await _entregar(cola, crudo)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception(f"[respuestas] {e}")
            # Sin esto, un Redis caído gira a máxima velocidad llenando el log.
            await asyncio.sleep(1.0)


async def _entregar(cola: str, crudo: str) -> None:
    try:
        res = desempacar(crudo)
    except VersionIncompatible as e:
        logging.error(f"[respuestas] contrato incompatible: {e}")
        return
    except Exception as e:
        logging.error(f"[respuestas] sobre ilegible en {cola}: {e}")
        return

    destino = res.responder_a or res.conversacion
    session = numeros.sesion_de(res.multiagente)

    if res.ok and res.texto:
        await waha.enviar_texto(session, destino, res.texto)
    elif not res.ok:
        # El usuario merece un «no pude». El silencio es peor que un error, y el
        # detalle técnico queda en el log, no en el chat.
        logging.error(f"[respuestas] turno {res.conversacion} falló: {res.error}")
        await waha.enviar_texto(
            session, destino,
            "No pude procesar tu consulta en este momento. Intentá de nuevo en "
            "unos minutos.",
        )

    # Los adjuntos van DESPUÉS del texto y de a uno: el texto explica qué son y
    # WhatsApp respeta el orden de envío. En paralelo llegarían desordenados.
    for archivo in res.media or []:
        await waha.enviar_media(session, destino, archivo)

    # Recién ahora se libera la conversación: el turno terminó de verdad, con la
    # respuesta ya en el chat. Si se soltara al encolar, un segundo mensaje
    # podría arrancar una corrida mientras la primera sigue.
    if res.lock:
        await acumulador.soltar_lock(res.multiagente, res.conversacion, res.lock)

    logging.info(
        f"[respuestas] {res.conversacion} · {res.duracion_ms} ms · ok={res.ok}"
        f"{f' · {len(res.media)} adjunto(s)' if res.media else ''}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sin token no se levanta. Ver recepcion/webhook.py.
    webhook.verificar_configuracion()

    propias = [ma for ma in MULTIAGENTES if numeros.SESIONES.get(ma)]
    if propias:
        logging.info(f"[recepcion] canales separados: {propias}")
    else:
        # Es el estado normal hoy, no una falla: un solo número atiende a los
        # tres y quién contesta lo decide el padrón. Se registra igual porque
        # explica por qué el canal no aparece en ninguna decisión de ruteo.
        logging.info(
            f"[recepcion] un solo número ({numeros.SESION_UNICA}) para los tres "
            f"multiagentes · rutea el padrón"
        )

    tareas = [asyncio.create_task(_drenar()), asyncio.create_task(_enviar_respuestas())]
    try:
        yield
    finally:
        for t in tareas:
            t.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
        await redis_mod.close()


app = FastAPI(title="Catusita — Recepción", lifespan=lifespan)
app.include_router(webhook.router_webhook, prefix="/webhook")


@app.get("/health")
async def health() -> dict:
    """Incluye el tamaño del padrón: un multiagente en cero es un contenedor
    que no arrancó, y sus usuarios están entrando como clientes ahora mismo."""
    return {
        "status": "ok",
        "servicio": "recepcion",
        "padron": await padron.tamano(),
        "sesiones": {ma: numeros.sesion_de(ma) for ma in MULTIAGENTES},
    }
