import os
import ssl
import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool = None


def _build_ssl(dsn: str):
    """Extrae sslmode del DSN y devuelve el contexto SSL adecuado."""
    if "sslmode=require" in dsn or "sslmode=verify" in dsn:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _strip_sslmode(dsn: str) -> str:
    """asyncpg no acepta sslmode= como parámetro de DSN; lo removemos."""
    import re
    return re.sub(r"[?&]sslmode=\w+", "", dsn)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raw_dsn = os.getenv("DATABASE_URL")
        ssl_ctx = _build_ssl(raw_dsn)
        clean_dsn = _strip_sslmode(raw_dsn)
        _pool = await asyncpg.create_pool(
            dsn=clean_dsn,
            ssl=ssl_ctx,
            min_size=2,
            max_size=10,
        )
    return _pool


async def init_db():
    pool = await get_pool()
    migration_path = os.path.join(os.path.dirname(__file__), "migrations", "001_initial.sql")
    with open(migration_path) as f:
        sql = f.read()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
