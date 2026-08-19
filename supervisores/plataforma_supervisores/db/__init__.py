"""Pool de Postgres. Uno por proceso. Nada más.

Está en `plataforma/` y no en cada área porque un pool es un recurso con estado
de proceso, igual que el de Redis: duplicarlo abriría N pools contra el mismo
Postgres sin ganar aislamiento.

El aislamiento NO lo da el pool, lo dan las tablas. `conocimiento_supervisores` y
`conocimiento_clientes` son tablas distintas, y cada área nombra solo la suya en
su `backend.py`. Con un pool compartido, `clientes` sigue sin poder llegar a los
procesos de `supervisores`: no tiene el nombre en ninguna parte de su paquete.

── Acá NO se corren migraciones ───────────────────────────────────────────────

Este módulo abre conexiones y nada más. No hay DDL en el arranque de ningún
worker, a propósito, por tres razones:

  1. HAY UNA SOLA BASE Y UN SOLO ESQUEMA. Las tablas están separadas por
     multiagente —`chat_messages_supervisores`, `conocimiento_clientes`— pero
     viven en la misma BD, y `migraciones` es una sola tabla para todas. Una
     migración no es «de supervisores»: la 008 renombró columnas en las tres
     tablas de conocimiento a la vez.

  2. LOS TRES WORKERS ARRANCAN JUNTOS. En cada deploy. Si los tres corrieran
     migraciones, serían tres procesos haciendo ALTER TABLE sobre la misma base
     al mismo tiempo. Es la clase de carrera que aparece una vez cada veinte
     deploys y deja el esquema a medias.

  3. EL QUE ATIENDE WHATSAPP NO DEBERÍA PODER BORRAR UNA TABLA. La 009 dropeó
     tres. Eso se corre mirando el resultado, no como efecto secundario de que
     un contenedor se reinició.

Los `.sql` de `db/migrations/` se aplican a mano, desde el entorno de
desarrollo, cuando se decide cambiar el esquema. La tabla `migraciones` sigue
siendo el registro de qué se aplicó.

── Lo que había antes ─────────────────────────────────────────────────────────

Un `migrar()` que corría al arrancar. Estaba roto de dos formas y ninguna daba
error:

    MIGRACIONES = Path(__file__).parent.parent.parent / "db" / "migrations"

resolvía a `supervisores/db/migrations`, que no existe — y `glob()` sobre un
directorio inexistente devuelve vacío. Corría cero migraciones en silencio. Y
aunque la ruta hubiera estado bien, el Dockerfile copia solo `supervisores/`, así
que `db/migrations` no está en la imagen.

O sea: la red de seguridad que parecía existir no existía. Mejor no tenerla que
creer que se tiene.
"""
import os
import re

import asyncpg
from dotenv import load_dotenv

load_dotenv()

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
