"""Persistencia del chat de Clientes. Su tabla y ninguna otra.

`chat_messages_clientes` es el ÚNICO nombre de tabla que aparece en este
paquete. La palabra «vendedores» no está escrita en ninguna parte de `clientes/`,
así que este código no puede leer ni escribir el chat del otro lado.

Se diferencia del de vendedores en quién es el dueño de la conversación: acá es
un RUC, no un vendedor_id. Un cliente se autentica con su RUC, y por eso el RUC
es la PK del roster y la FK de esta tabla.
"""
from plataforma import db

TABLA = "chat_messages_clientes"


async def guardar(
    numero: str,
    rol: str,
    contenido: str,
    cliente_ruc: str | None = None,
    cliente_nombre: str | None = None,
    session_id: str | None = None,
    tipo: str = "texto",
    tools: list | None = None,
    latencia_ms: int | None = None,
) -> str | None:
    """Guarda un mensaje y devuelve su id, para `solicitud_proceso_nuevo_clientes`.

    Ojo con `cliente_ruc`: va NULL mientras el cliente no se haya identificado.
    Es el caso normal en los primeros mensajes de una conversación — el agente
    todavía no sabe quién es. Por eso la FK admite NULL.
    """
    pool = await db.get()
    async with pool.acquire() as c:
        return await c.fetchval(
            f"""INSERT INTO {TABLA}
                  (numero, rol, contenido, cliente_ruc, cliente_nombre,
                   session_id, tipo, tools, latencia_ms)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                RETURNING id""",
            numero, rol, contenido, cliente_ruc, cliente_nombre,
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
