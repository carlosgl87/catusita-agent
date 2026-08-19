"""Persistencia del chat de Supervisores. Su tabla y ninguna otra.

`chat_messages_supervisores` es el ÚNICO nombre de tabla de este paquete.

Todavía sin tráfico: este multiagente tiene una sola área (`conocimiento`) y su
alcance está sin definir —ver supervisores/orquestador.py, la pregunta abierta
de si un supervisor puede ver la cartera de SUS asesores. La tabla y este módulo
existen para que el día que se defina, no haya que inventar dónde guardar.
"""
from supervisores.plataforma_supervisores import db

TABLA = "chat_messages_supervisores"


async def guardar(
    numero: str,
    rol: str,
    contenido: str,
    supervisor_id: str | None = None,
    supervisor_nombre: str | None = None,
    session_id: str | None = None,
    tipo: str = "texto",
    tools: list | None = None,
    latencia_ms: int | None = None,
) -> str | None:
    """Guarda un mensaje y devuelve su id, para `solicitud_proceso_nuevo_supervisores`."""
    pool = await db.get()
    async with pool.acquire() as c:
        return await c.fetchval(
            f"""INSERT INTO {TABLA}
                  (numero, rol, contenido, supervisor_id, supervisor_nombre,
                   session_id, tipo, tools, latencia_ms)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                RETURNING id""",
            numero, rol, contenido, supervisor_id, supervisor_nombre,
            session_id, tipo, tools or [], latencia_ms,
        )


async def historial(numero: str, limite: int = 500) -> list[dict]:
    """Histórico persistente para el panel. Lo que lee el agente sale de Redis."""
    pool = await db.get()
    async with pool.acquire() as c:
        filas = await c.fetch(
            f"""SELECT rol, contenido, tipo, tools, created_at
                  FROM {TABLA} WHERE numero = $1
                 ORDER BY created_at ASC LIMIT $2""",
            numero, limite,
        )
    return [dict(f) for f in filas]
