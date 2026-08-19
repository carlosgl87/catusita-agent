"""Subgrafo de `conocimiento` (vendedores).

Salidas permitidas (las fuerza vendedores/grafo.py):
  - SOLO vuelve al orquestador
  - NO va a otra área
  - NO va a END: toda respuesta pasa por validar
"""
from vendedores.agentes.conocimiento.prompt import SYSTEM  # noqa: F401
from vendedores.agentes.conocimiento.tools import TOOLS  # noqa: F401

NODO = None  # TODO: StateGraph propio, compilado con MODELO y TOOLS
