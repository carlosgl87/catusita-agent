"""Pool de Postgres y corredor de migraciones. Uno por proceso.

Está en `plataforma/` y no en cada multiagente porque un pool es un recurso con
estado de proceso, igual que el de Redis: duplicarlo abriría N pools contra el
mismo Postgres sin ganar aislamiento.

El aislamiento NO lo da el pool, lo dan las tablas. `conocimiento_vendedores` y
`conocimiento_clientes` son tablas distintas, y cada área nombra solo la suya en
su `backend.py`. Con un pool compartido, `clientes` sigue sin poder llegar a los
procesos de `vendedores`: no tiene el nombre en ninguna parte de su paquete.

Migrado desde db/connection.py, con dos correcciones.
"""
import logging
import os
import re
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

MIGRACIONES = Path(__file__).parent.parent.parent / "db" / "migrations"

_pool: asyncpg.Pool | None = None


def _sin_sslmode(dsn: str) -> str:
    """Railway mete sslmode en la URL y asyncpg no lo entiende — lo pasa por ssl=."""
    return re.sub(r"[?&]sslmode=\w+", "", dsn)


async def get() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("Falta DATABASE_URL.")
        _pool = await asyncpg.create_pool(
            _sin_sslmode(dsn), ssl="require", min_size=2, max_size=10
        )
    return _pool


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def migrar() -> list[str]:
    """Corre las migraciones que faltan. Devuelve cuáles corrió.

    ── Por qué lleva registro y no reejecuta todo ─────────────────────────────

    La versión anterior (db/connection.py::init_db) corría TODAS las migraciones
    en cada arranque, confiando en que los `CREATE TABLE IF NOT EXISTS` la
    hicieran idempotente. No lo era:

      - Las tablas que se dropeaban a mano volvían a crearse en el siguiente
        deploy. Sin error, sin log. Se borraron `users`, `conversations`,
        `messages` y `claims` y habrían reaparecido solas.

      - Un `ALTER TABLE ... ADD CONSTRAINT` no tiene `IF NOT EXISTS`: al segundo
        arranque tira error y tumba el startup entero.

    Con la tabla `migraciones`, cada archivo corre UNA vez y queda anotado. Es
    también lo que permite escribir migraciones destructivas (DROP, ALTER) sin
    miedo a que se repitan.

    Cada migración va en su propia transacción: si la 005 falla, la 004 ya
    aplicada no se revierte y el arranque falla con un mensaje claro.
    """
    pool = await get()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS migraciones (
                nombre     TEXT PRIMARY KEY,
                aplicada_at TIMESTAMP DEFAULT NOW()
            )
        """)
        ya = {r["nombre"] for r in await conn.fetch("SELECT nombre FROM migraciones")}

    corridas = []
    for f in sorted(MIGRACIONES.glob("*.sql")):
        if f.name in ya:
            continue
        sql = f.read_text(encoding="utf-8")
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO migraciones (nombre) VALUES ($1)", f.name
                )
        corridas.append(f.name)
        logging.info(f"migración aplicada: {f.name}")

    return corridas


async def marcar_aplicadas(nombres: list[str]) -> None:
    """Anota migraciones como ya corridas SIN ejecutarlas.

    Para el arranque en una base que ya tiene el esquema puesto a mano —que es
    exactamente el caso de 001 a 004 acá: se aplicaron directo contra Railway
    antes de que existiera este corredor. Sin esto, el primer `migrar()` las
    reejecutaría.
    """
    pool = await get()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS migraciones (
                nombre     TEXT PRIMARY KEY,
                aplicada_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.executemany(
            "INSERT INTO migraciones (nombre) VALUES ($1) ON CONFLICT DO NOTHING",
            [(n,) for n in nombres],
        )
