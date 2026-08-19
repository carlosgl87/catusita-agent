"""Consultas del PANEL. No las usa ningún agente.

El panel es la vista de administración: mira los datos de los tres multiagentes,
y eso NO rompe el aislamiento — el aislamiento es entre agentes, no entre el
agente y quien lo supervisa.

Cada multiagente escribe en SU tabla a través de su propio módulo
(`vendedores/chat.py`, `clientes/chat.py`, `supervisores/chat.py`). Acá solo se
LEE, y por ahora solo la de vendedores: es el único con tráfico.

Cuando clientes y supervisores tengan mensajes, estas consultas pasan a recibir
la tabla por parámetro en vez de tenerla fija en TABLA.

No usa ORM — queries directas con asyncpg.
"""
from datetime import datetime, date
from db.connection import get_pool

# Antes era `chat_messages`, una sola tabla con columna `canal`. Ahora hay una
# por multiagente (migración 005) y el panel lee la de vendedores.
TABLA = "chat_messages_vendedores"




# save_chat_message() se retiró: ESCRIBIR es de cada multiagente.
#
#     vendedores/chat.py::guardar()     -> chat_messages_vendedores
#     clientes/chat.py::guardar()       -> chat_messages_clientes
#     supervisores/chat.py::guardar()   -> chat_messages_supervisores
#
# Tener el INSERT acá era justamente lo que hacía que los tres escribieran en la
# misma tabla. Y las de allá devuelven el id de la fila, que hace falta para
# `solicitud_proceso_nuevo_*.mensaje_id`.


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


def _to_date(s):
    """Convierte 'YYYY-MM-DD' a datetime.date (asyncpg necesita el objeto, no el string)."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _filtros(vendedor_id, desde, hasta):
    # desde/hasta son fechas de calendario en hora de Lima, ambas inclusivas.
    conds, params = [], []
    if vendedor_id:
        params.append(vendedor_id); conds.append(f"vendedor_id = ${len(params)}")
    d = _to_date(desde)
    if d:
        params.append(d); conds.append(f"{_LIMA}::date >= ${len(params)}")
    h = _to_date(hasta)
    if h:
        params.append(h); conds.append(f"{_LIMA}::date <= ${len(params)}")
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
                  FROM {TABLA} {where}""",
            *params,
        )
    return {"mensajes_totales": row["mensajes_totales"], "conversaciones": row["conversaciones"]}


async def stats_evolucion(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where(["rol = 'user'"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT date_trunc('week', {_LIMA})::date AS semana, COUNT(*) AS mensajes
                  FROM {TABLA} {where} GROUP BY 1 ORDER BY 1""",
            *params,
        )
    return [{"semana": r["semana"].isoformat(), "mensajes": r["mensajes"]} for r in rows]


async def stats_por_dia(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where(["rol = 'user'"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT EXTRACT(ISODOW FROM {_LIMA})::int AS dia, COUNT(*) AS n
                  FROM {TABLA} {where} GROUP BY 1 ORDER BY 1""",
            *params,
        )
    return [{"dia": r["dia"], "n": r["n"]} for r in rows]


async def stats_por_hora(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where(["rol = 'user'"], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT EXTRACT(HOUR FROM {_LIMA})::int AS hora, COUNT(*) AS n
                  FROM {TABLA} {where} GROUP BY 1 ORDER BY 1""",
            *params,
        )
    return [{"hora": r["hora"], "n": r["n"]} for r in rows]


async def stats_tools(vendedor_id=None, desde=None, hasta=None) -> list:
    where, params = _where([], vendedor_id, desde, hasta)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT t AS tool, COUNT(*) AS n
                  FROM {TABLA}, unnest(tools) t {where}
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
                  FROM {TABLA} {where}
                 GROUP BY vendedor_id ORDER BY mensajes DESC""",
            *params,
        )
    return [{"vendedor_id": r["vendedor_id"], "nombre": r["nombre"], "mensajes": r["mensajes"]} for r in rows]


async def stats_sin_uso() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT v.vendedor_id, v.nombre FROM vendedores v
                WHERE v.activo AND NOT EXISTS (
                    SELECT 1 FROM {TABLA} m
                     WHERE m.vendedor_id = v.vendedor_id AND m.rol = 'user')
                ORDER BY v.nombre"""
        )
    return [{"vendedor_id": r["vendedor_id"], "nombre": r["nombre"]} for r in rows]


async def list_chats() -> list:
    """Lista de conversaciones: numero, cantidad, último mensaje y fecha."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT m.numero,
                   COUNT(*)                              AS n,
                   MAX(m.created_at)                     AS last_ts,
                   (SELECT contenido FROM {TABLA} x
                     WHERE x.numero = m.numero
                     ORDER BY x.created_at DESC LIMIT 1) AS last_msg
              FROM {TABLA} m
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
            f"""SELECT rol, contenido, created_at
                 FROM {TABLA}
                WHERE numero = $1
                ORDER BY created_at ASC
                LIMIT $2""",
            numero, limit,
        )
    return [dict(r) for r in rows]
