import json
import os
import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TTL_SECONDS = 7200  # 2 horas
MAX_MESSAGES = 20   # 10 turnos (user + assistant)

_redis = None


async def _get_redis():
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _key(numero: str) -> str:
    return f"conversation:{numero}"


async def get_history(numero: str) -> list:
    try:
        r = await _get_redis()
        raw = await r.get(_key(numero))
        return json.loads(raw) if raw else []
    except Exception:
        return []


async def save_message(numero: str, rol: str, contenido: str):
    try:
        r = await _get_redis()
        historial = await get_history(numero)
        historial.append({"role": rol, "content": contenido})
        if len(historial) > MAX_MESSAGES:
            historial = historial[-MAX_MESSAGES:]
        await r.setex(_key(numero), TTL_SECONDS, json.dumps(historial, ensure_ascii=False))
    except Exception:
        pass


async def clear_history(numero: str):
    try:
        r = await _get_redis()
        await r.delete(_key(numero))
    except Exception:
        pass
