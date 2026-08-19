"""Persistencia del chat de Vendedores. Su tabla y ninguna otra.

`chat_messages_vendedores` es el ÚNICO nombre de tabla que aparece en este
paquete. No hay forma de que este código escriba o lea el chat de clientes: no
tiene el nombre escrito en ningún lado.

Es el mismo criterio que `agentes/*/backend.py`: la plomería (el pool) viene de
`plataforma/`, pero qué tabla se toca lo decide el multiagente.

── Por qué devuelve el id ─────────────────────────────────────────────────────

`guardar()` devuelve el UUID de la fila para que cualquier cosa que quiera
apuntar a un mensaje concreto —telemetría, análisis de conversaciones, una
revisión posterior— pueda referenciarlo en vez de copiar número y texto.

Y por eso el mensaje del usuario se guarda ANTES de correr el agente, no después
como hacía webhooks/whatsapp.py: el id tiene que existir cuando el grafo corre.
Además arregla algo que ya estaba mal — si el agente reventaba, el mensaje del
usuario se perdía de la BD.
"""
from vendedores.plataforma_vendedores import db

TABLA = "chat_messages_vendedores"


async def guardar(
    numero: str,
    rol: str,
    contenido: str,
    vendedor_id: str | None = None,
    vendedor_nombre: str | None = None,
    session_id: str | None = None,
    tipo: str = "texto",
    tools: list | None = None,
    latencia_ms: int | None = None,
) -> str | None:
    """Guarda un mensaje y devuelve su id. None si la BD falla.

    Que devuelva None en vez de reventar es deliberado: no poder registrar un
    mensaje degrada la telemetría, pero no es motivo para dejar sin contestar a
    un asesor. El id None simplemente deja la solicitud sin `mensaje_id`.
    """
    pool = await db.get()
    async with pool.acquire() as c:
        return await c.fetchval(
            f"""INSERT INTO {TABLA}
                  (numero, rol, contenido, vendedor_id, vendedor_nombre,
                   session_id, tipo, tools, latencia_ms)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                RETURNING id""",
            numero, rol, contenido, vendedor_id, vendedor_nombre,
            session_id, tipo, tools or [], latencia_ms,
        )


async def historial(numero: str, limite: int = 500) -> list[dict]:
    """Mensajes de una conversación, en orden cronológico.

    Esto NO es lo que lee el agente —eso sale de Redis, ver
    plataforma/nodos/contexto.py— es el histórico persistente para el panel.
    """
    pool = await db.get()
    async with pool.acquire() as c:
        filas = await c.fetch(
            f"""SELECT rol, contenido, tipo, tools, created_at
                  FROM {TABLA} WHERE numero = $1
                 ORDER BY created_at ASC LIMIT $2""",
            numero, limite,
        )
    return [dict(f) for f in filas]
