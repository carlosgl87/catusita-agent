"""Subgrafo de `recomendaciones` (clientes).

Nodo del grafo de Clientes, con estado propio. Sus mensajes internos no
suben al historial: al orquestador solo le llega el resultado.

Salidas permitidas (las fuerza clientes/grafo.py):
  - SOLO vuelve a `supervisor`
  - NO va a otra área
  - NO va a END: toda respuesta pasa por `validar`

Si le falta un dato de otra área NO la llama: termina su turno
diciendo qué necesita, y el orquestador decide.

    falta para el catálogo
      -> lo tiene `productos`
"""
from clientes.agentes.recomendaciones.prompt import SYSTEM  # noqa: F401
from clientes.agentes.recomendaciones.tools import TOOLS  # noqa: F401

NODO = None  # TODO: StateGraph propio, compilado con MODELO y TOOLS
