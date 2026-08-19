"""Subgrafo de `conocimiento` (clientes).

Salidas permitidas (las fuerza clientes/grafo.py):
  - SOLO vuelve al orquestador
  - NO va a otra área
  - NO va a END: toda respuesta pasa por validar
"""
from clientes.agentes.conocimiento.prompt import SYSTEM  # noqa: F401
from clientes.agentes.conocimiento.tools import TOOLS  # noqa: F401

NODO = None  # TODO: StateGraph propio, compilado con MODELO y TOOLS
