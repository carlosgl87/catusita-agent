"""Subgrafo de `productos` (vendedores).

Nodo del grafo de Vendedores, con estado propio. Sus mensajes internos no
suben al historial: al orquestador solo le llega el resultado.

Salidas permitidas (las fuerza vendedores/grafo.py):
  - SOLO vuelve a `supervisor`
  - NO va a otra área
  - NO va a END: toda respuesta pasa por `validar`
"""
from vendedores.agentes.productos.prompt import SYSTEM  # noqa: F401
from vendedores.agentes.productos.tools import TOOLS  # noqa: F401

NODO = None  # TODO: StateGraph propio, compilado con MODELO y TOOLS
