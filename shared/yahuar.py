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

YAHUAR_NUMBER  = os.getenv("YAHUAR_NUMBER", "51977504279")
YAHUAR_CHAT_ID = f"{YAHUAR_NUMBER}@c.us"
PENDING_KEY    = "yahuar:pendiente"
PENDING_TTL    = 180   # 3 min
YAHUAR_LID_KEY = "yahuar:lid"   # LID aprendido automáticamente la primera vez que responde


async def consultar_placa(placa: str, from_field: str) -> None:
    """Guarda en Redis quién preguntó y envía la placa a Yahuar."""
    from shared import waha as waha_mod   # import tardío para evitar circular
    r = await _get_redis()
    data = json.dumps(
        {"from_field": from_field, "placa": placa.upper(), "ts": time.time()},
        ensure_ascii=False,
    )
    await r.setex(PENDING_KEY, PENDING_TTL, data)
    await waha_mod.waha.send_message(YAHUAR_CHAT_ID, "", placa.upper())


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
