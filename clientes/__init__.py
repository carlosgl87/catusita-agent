"""Multiagente Clientes — Talleres, distribuidores y consumidor final.

Solo información pública: stock, precio de lista, catálogo y reclamos.

Es un proyecto aparte de `vendedores` y `supervisores`. No comparten agentes, ni
prompts, ni acceso a datos: solo `plataforma/` (LLM, Redis, DB, transporte) y el
`router/` que decide a cuál de los tres entra el mensaje.

Áreas: productos, vehiculos, postventa, recomendaciones, conocimiento
"""

# La cola de este multiagente. Es la ÚNICA frontera de proceso que hay: el
# webhook encola acá y el worker levanta el turno. De ahí para adentro
# —orquestador y áreas— todo corre en el mismo proceso.
#
# Las áreas NO tienen cola. Son nodos del mismo grafo y el orquestador las
# invoca con Command(goto=...), que es un salto en memoria. Meter Redis entre
# el orquestador y un área obligaría a ejecución durable con checkpoints, y se
# perdería justamente el mecanismo con el que las controla.
COLA = "clientes"
