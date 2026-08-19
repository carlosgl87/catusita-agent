"""Pool de Redis. Uno por proceso.

Es de las pocas cosas que están en `plataforma/` y no en un área: duplicar el
pool abriría N conexiones contra el mismo Redis sin ganar aislamiento.

Migrado desde orchestrator/context.py::_get_redis.
"""
import os

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_pool: aioredis.Redis | None = None


async def get() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
