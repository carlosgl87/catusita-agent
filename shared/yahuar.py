"""
Relay de consulta de placas vía Yahuar WhatsApp (51977504279).

Flujo:
1. consultar_placa(placa, from_field) → envía la placa a Yahuar + guarda en Redis
   quién está esperando la respuesta.
2. El webhook detecta que llegó un mensaje de Yahuar, llama a get_pendiente()
   y reenvía el texto + foto al usuario original.
"""
import json
import os
import time

from orchestrator.context import _get_redis

YAHUAR_NUMBER    = os.getenv("YAHUAR_NUMBER", "51977504279")
YAHUAR_CHAT_ID   = f"{YAHUAR_NUMBER}@c.us"
PENDING_KEY      = "yahuar:pendiente"
PENDING_TTL      = 180   # 3 min
YAHUAR_LID_KEY   = "yahuar:lid"     # LID aprendido automáticamente
RELAY_DEST_KEY   = "yahuar:relay"   # destino activo mientras llegan follow-ups (texto + foto)
RELAY_DEST_TTL   = 45               # segundos que esperamos mensajes adicionales de Yahuar
BUFFER_KEY       = "yahuar:buf"     # acumula texto + imagen antes de procesar
BUFFER_TTL       = 20               # ventana para que llegue la imagen después del texto
IMG_DONE_KEY     = "yahuar:imgdone" # flag: imagen ya procesada (evita doble envío)


async def consultar_placa(placa: str, from_field: str) -> None:
    """Guarda en Redis quién preguntó y envía la placa a Yahuar."""
    from shared import waha as waha_mod   # import tardío para evitar circular
    r = await _get_redis()
    data = json.dumps(
        {"from_field": from_field, "placa": placa.upper(), "ts": time.time()},
        ensure_ascii=False,
    )
    await r.setex(PENDING_KEY, PENDING_TTL, data)
    # Mandamos la placa con contexto para que Yahuar no pida aclaración
    await waha_mod.waha.send_message(YAHUAR_CHAT_ID, "", f"Placa vehicular: {placa.upper()}")


async def peek_pendiente() -> dict | None:
    """Lee la consulta pendiente SIN eliminarla."""
    r = await _get_redis()
    raw = await r.get(PENDING_KEY)
    return json.loads(raw) if raw else None


async def get_yahuar_lid() -> str | None:
    """Devuelve el LID aprendido de Yahuar, o None si aún no se conoce."""
    r = await _get_redis()
    val = await r.get(YAHUAR_LID_KEY)
    return val.decode() if isinstance(val, bytes) else val


async def save_yahuar_lid(numero: str) -> None:
    """Guarda el LID de Yahuar en Redis sin expiración (aprendizaje permanente)."""
    r = await _get_redis()
    await r.set(YAHUAR_LID_KEY, numero)
    print(f"[YAHUAR] LID aprendido y guardado: {numero!r}", flush=True)


async def open_relay(from_field: str) -> None:
    """Abre una ventana de relay de 45s para recibir mensajes follow-up de Yahuar (ej. foto)."""
    r = await _get_redis()
    await r.setex(RELAY_DEST_KEY, RELAY_DEST_TTL, from_field)


async def get_relay_dest() -> str | None:
    """Devuelve el destino activo del relay, o None si ya expiró."""
    r = await _get_redis()
    val = await r.get(RELAY_DEST_KEY)
    return val.decode() if isinstance(val, bytes) else val


async def buffer_texto(texto: str) -> None:
    """Guarda el texto de Yahuar en el buffer esperando que llegue la imagen."""
    r = await _get_redis()
    await r.setex(BUFFER_KEY, BUFFER_TTL, texto)


async def get_buffer_texto() -> str | None:
    r = await _get_redis()
    val = await r.get(BUFFER_KEY)
    return val.decode() if isinstance(val, bytes) else val


async def marcar_imagen_procesada() -> None:
    r = await _get_redis()
    await r.setex(IMG_DONE_KEY, BUFFER_TTL, "1")
    await r.delete(BUFFER_KEY)


async def imagen_ya_procesada() -> bool:
    r = await _get_redis()
    return bool(await r.get(IMG_DONE_KEY))


async def get_pendiente() -> dict | None:
    """
    Obtiene y elimina la consulta pendiente de Redis.
    Retorna {from_field, placa, ts} o None si no hay ninguna.
    """
    r = await _get_redis()
    raw = await r.get(PENDING_KEY)
    if raw:
        await r.delete(PENDING_KEY)
        return json.loads(raw)
    return None
