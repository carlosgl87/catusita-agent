"""
Helpers para insertar y consultar registros en las tablas principales.
No usa ORM — queries directas con asyncpg para máxima velocidad.
"""
import uuid
from datetime import datetime
from db.connection import get_pool


async def get_user_by_whatsapp(numero: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE whatsapp_number = $1 AND activo = true", numero
        )
    return dict(row) if row else None


async def get_user_by_ruc(ruc: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE ruc = $1 AND activo = true", ruc
        )
    return dict(row) if row else None


async def create_conversation(user_id: str, agente_tipo: str, numero: str) -> str:
    pool = await get_pool()
    conv_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO conversations (id, user_id, agente_tipo, numero_whatsapp)
               VALUES ($1, $2, $3, $4)""",
            conv_id, user_id, agente_tipo, numero,
        )
    return conv_id


async def save_message(conversation_id: str, rol: str, contenido: str, tool_name: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO messages (id, conversation_id, rol, contenido, tool_name)
               VALUES ($1, $2, $3, $4, $5)""",
            str(uuid.uuid4()), conversation_id, rol, contenido, tool_name,
        )


async def create_claim(conversation_id: str, pedido_id: str, motivo: str) -> str:
    pool = await get_pool()
    numero = f"REC-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO claims (id, numero_reclamo, conversation_id, pedido_id, motivo)
               VALUES ($1, $2, $3, $4, $5)""",
            str(uuid.uuid4()), numero, conversation_id, pedido_id, motivo,
        )
    return numero
