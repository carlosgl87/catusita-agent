import os
import re
import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool = None


def _strip_sslmode(dsn: str) -> str:
    return re.sub(r"[?&]sslmode=\w+", "", dsn)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = _strip_sslmode(os.getenv("DATABASE_URL"))
        _pool = await asyncpg.create_pool(dsn, ssl="require", min_size=2, max_size=10)
    return _pool


async def init_db():
    pool = await get_pool()
    mig_dir = os.path.join(os.path.dirname(__file__), "migrations")
    # Corre todas las migraciones *.sql en orden alfabético (001, 002, ...).
    # Son idempotentes (CREATE ... IF NOT EXISTS), así que es seguro cada arranque.
    for name in sorted(os.listdir(mig_dir)):
        if not name.endswith(".sql"):
            continue
        with open(os.path.join(mig_dir, name)) as f:
            sql = f.read()
        async with pool.acquire() as conn:
            await conn.execute(sql)


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
