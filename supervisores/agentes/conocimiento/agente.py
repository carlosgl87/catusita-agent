"""Subgrafo de `conocimiento` (supervisores).

Salidas permitidas (las fuerza supervisores/grafo.py):
  - SOLO vuelve al orquestador
  - NO va a otra área
  - NO va a END: toda respuesta pasa por validar
"""
from supervisores.agentes.conocimiento.prompt import SYSTEM  # noqa: F401
from supervisores.agentes.conocimiento.tools import TOOLS  # noqa: F401

NODO = None  # TODO: StateGraph propio, compilado con MODELO y TOOLS
