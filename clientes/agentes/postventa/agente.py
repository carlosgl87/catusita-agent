"""Subgrafo de `postventa` (clientes).

Nodo del grafo de Clientes, con estado propio. Sus mensajes internos no
suben al historial: al orquestador solo le llega el resultado.

Salidas permitidas (las fuerza clientes/grafo.py):
  - SOLO vuelve a `supervisor`
  - NO va a otra área
  - NO va a END: toda respuesta pasa por `validar`
"""
from clientes.agentes.postventa.prompt import SYSTEM  # noqa: F401
from clientes.agentes.postventa.tools import TOOLS  # noqa: F401

NODO = None  # TODO: StateGraph propio, compilado con MODELO y TOOLS
