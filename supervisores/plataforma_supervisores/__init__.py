"""Infraestructura compartida por los dos multiagentes. Deliberadamente mínima.

Es lo ÚNICO que `vendedores/` y `clientes/` tienen en común:

    estado.py     el TypedDict que viaja por cualquiera de los dos grafos
    nodos/        contexto (historial) y validar (guardián de salida)
    llm.py        cliente Anthropic
    redis.py      pool de conexiones
    db/           pool de Postgres

Acá NO hay lógica de negocio ni acceso a las BACKEND APIS. Cada área de cada
multiagente tiene su propio `backend.py`, y por eso el de clientes puede no mapear
`precio_neto` mientras el de vendedores sí.

Criterio para que algo entre: si es un recurso con estado de proceso (un pool,
un cliente con rate limit), va acá. Si es conocimiento de negocio, va en el área.
"""
