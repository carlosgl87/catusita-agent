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


async def log_tool_usage(conversation_id: str, vendedor_id: str,
                         tool_name: str, duracion_ms: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO tool_usage (conversation_id, vendedor_id, tool_name, duracion_ms)
               VALUES ($1, $2, $3, $4)""",
            conversation_id, vendedor_id, tool_name, duracion_ms,
        )


async def save_chat_message(
    numero: str,
    rol: str,
    contenido: str,
    vendedor_id: str = None,
    vendedor_nombre: str = None,
    canal: str = "vendedor",
    session_id: str = None,
    tipo: str = "texto",
    tools: list = None,
    latencia_ms: int = None,
) -> None:
    """Guarda un mensaje/evento en chat_messages con sus dimensiones para estadísticas."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO chat_messages
                 (numero, rol, contenido, vendedor_id, vendedor_nombre, canal,
                  session_id, tipo, tools, latencia_ms)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            numero, rol, contenido, vendedor_id, vendedor_nombre, canal,
            session_id, tipo, tools or [], latencia_ms,
        )


# ─── Roster de vendedores ─────────────────────────────────────────────────────

async def upsert_vendedor(vendedor_id: str, codigo: str, nombre: str,
                          whatsapp: str = None, n_clientes: int = None) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO vendedores (vendedor_id, codigo, nombre, whatsapp, n_clientes, activo)
               VALUES ($1,$2,$3,$4,$5,true)
               ON CONFLICT (vendedor_id) DO UPDATE
                 SET codigo=$2, nombre=$3, whatsapp=$4, n_clientes=COALESCE($5, vendedores.n_clientes),
                     activo=true""",
            vendedor_id, codigo, nombre, whatsapp, n_clientes,
        )


async def list_vendedores() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT vendedor_id, nombre FROM vendedores WHERE activo ORDER BY nombre"
        )
    return [dict(r) for r in rows]


# ─── Estadísticas (todas con filtro vendedor_id / desde / hasta) ──────────────

# created_at se guarda ~UTC; se convierte a hora de Lima para día/hora/semana.
_LIMA = "(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/Lima')"


def _filtros(vendedor_id, desde, hasta):
    # desde/hasta son fechas de calendario en hora de Lima, ambas inclusivas.
    conds, params = [], []
    if vendedor_id:
        params.append(vendedor_id); conds.append(f"vendedor_id = ${len(params)}")
    if desde:
        params.append(desde); conds.append(f"{_LIMA}::date >= ${len(params)}::date")
    if hasta:
        params.append(hasta); conds.append(f"{_LIMA}::date <= ${len(params)}::date")
    return conds, params


def _where(extra, vendedor_id, desde, hasta):
    conds, params = _filtros(vendedor_id, desde, hasta)
    conds = list(extra) + conds
    return ("WHERE " + " AND ".join(conds)) if conds else "", params


async def stats_resumen(vendedor_id=None, desde=None, hasta=None) -> dict:
    where, params = _where(["rol = 'user'"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""SELECT COUNT(*) AS mensajes_totales,
                       COUNT(DISTINCT numero || '|' || ({_LIMA}::date)::text) AS conversaciones
                  FROM chat_messages {where}""",
            *params,
        )
    return {"mensajes_totales": row["mensajes_totales"], "conversaciones": row["conversaciones"]}


async def stats_evolucion(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where(["rol = 'user'"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT date_trunc('week', {_LIMA})::date AS semana, COUNT(*) AS mensajes
                  FROM chat_messages {where} GROUP BY 1 ORDER BY 1""",
            *params,
        )
    return [{"semana": r["semana"].isoformat(), "mensajes": r["mensajes"]} for r in rows]


async def stats_por_dia(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where(["rol = 'user'"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT EXTRACT(ISODOW FROM {_LIMA})::int AS dia, COUNT(*) AS n
                  FROM chat_messages {where} GROUP BY 1 ORDER BY 1""",
            *params,
        )
    return [{"dia": r["dia"], "n": r["n"]} for r in rows]


async def stats_por_hora(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where(["rol = 'user'"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT EXTRACT(HOUR FROM {_LIMA})::int AS hora, COUNT(*) AS n
                  FROM chat_messages {where} GROUP BY 1 ORDER BY 1""",
            *params,
        )
    return [{"hora": r["hora"], "n": r["n"]} for r in rows]


async def stats_tools(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where([], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT t AS tool, COUNT(*) AS n
                  FROM chat_messages, unnest(tools) t {where}
                 GROUP BY 1 ORDER BY n DESC""",
            *params,
        )
    total = sum(r["n"] for r in rows) or 1
    return [{"tool": r["tool"], "n": r["n"], "pct": round(100 * r["n"] / total)} for r in rows]


async def stats_ranking(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where(["rol = 'user'", "vendedor_id IS NOT NULL"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT vendedor_id, MAX(vendedor_nombre) AS nombre, COUNT(*) AS mensajes
                  FROM chat_messages {where}
                 GROUP BY vendedor_id ORDER BY mensajes DESC""",
            *params,
        )
    return [{"vendedor_id": r["vendedor_id"], "nombre": r["nombre"], "mensajes": r["mensajes"]} for r in rows]


async def stats_sin_uso() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT v.vendedor_id, v.nombre FROM vendedores v
                WHERE v.activo AND NOT EXISTS (
                    SELECT 1 FROM chat_messages m
                     WHERE m.vendedor_id = v.vendedor_id AND m.rol = 'user')
                ORDER BY v.nombre"""
        )
    return [{"vendedor_id": r["vendedor_id"], "nombre": r["nombre"]} for r in rows]


async def list_chats() -> list:
    """Lista de conversaciones: numero, cantidad, último mensaje y fecha."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT m.numero,
                   COUNT(*)                              AS n,
                   MAX(m.created_at)                     AS last_ts,
                   (SELECT contenido FROM chat_messages x
                     WHERE x.numero = m.numero
                     ORDER BY x.created_at DESC LIMIT 1) AS last_msg
              FROM chat_messages m
             GROUP BY m.numero
             ORDER BY last_ts DESC
            """
        )
    return [dict(r) for r in rows]


async def get_chat_messages(numero: str, limit: int = 500) -> list:
    """Mensajes de una conversación, en orden cronológico."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT rol, contenido, created_at
                 FROM chat_messages
                WHERE numero = $1
                ORDER BY created_at ASC
                LIMIT $2""",
            numero, limit,
        )
    return [dict(r) for r in rows]


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
