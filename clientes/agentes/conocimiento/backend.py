"""Acceso de `conocimiento` (clientes) a los procesos.

No habla con las BACKEND APIS: habla con Postgres + pgvector, tablas
`conocimiento_clientes` y `solicitud_proceso_nuevo_clientes`
(ver db/migrations/004_conocimiento.sql — SIN APLICAR).

Ya NO lleva filtro por multiagente. La tabla ES la de clientes: la frontera dejó de
ser un WHERE que alguien puede olvidar y pasó a ser el nombre de la tabla. Un
proceso de otro multiagente no puede salir de acá ni con el query mal escrito.

    SELECT titulo, cuando, pasos, entrega, 1 - (embedding <=> $1) AS similitud
      FROM conocimiento_clientes
     WHERE activo
     ORDER BY embedding <=> $1
     LIMIT $2
"""
from clientes.plataforma_clientes.embeddings import MODELO as MODELO_EMBEDDING, embeber  # noqa: F401

TABLA_PROCESOS   = "conocimiento_clientes"
TABLA_SOLICITUD  = "solicitud_proceso_nuevo_clientes"

# `embeber` se reexporta desde plataforma: el cliente de OpenAI es uno por
# proceso, no uno por área. El aislamiento entre multiagentes lo dan las tablas
# de arriba, no el cliente.
#
# MODELO_EMBEDDING viaja hasta la columna `modelo_emb` de cada fila. Es lo que
# permite saber qué quedó viejo si algún día se cambia de modelo.


async def similares(vector: list[float], k: int = 5) -> list[dict]:
    """Top-k de `conocimiento_clientes`. [{titulo, cuando, pasos, entrega, similitud}]"""
    raise NotImplementedError


async def registrar_solicitud(
    consulta: str,
    vector: list[float],
    origen: str,              # 'sin_resultado' | 'rechazado'
    mensaje_id: str | None = None,
    mejor_sim: float | None = None,
    motivo: str | None = None,
) -> None:
    """Deja constancia de un proceso que falta, en `solicitud_proceso_nuevo_clientes`.

    AGRUPA, NO ACUMULA. Antes de insertar busca una solicitud PENDIENTE cuyo
    embedding esté cerca; si la hay, le suma `veces` y actualiza `ultima_vez`.
    Sin eso, la misma carencia abre veinte filas con veinte redacciones y la
    lista deja de servir para priorizar.

    NO PUEDE TUMBAR LA CONVERSACIÓN. Corre fuera del camino de la respuesta y si
    falla se loguea y se sigue: no registrar una solicitud no es motivo para
    dejar sin contestar a un asesor.

    TODO: implementar. El UPSERT por similitud va en una sola sentencia para que
    dos mensajes simultáneos no abran dos filas de lo mismo.
    """
    raise NotImplementedError
