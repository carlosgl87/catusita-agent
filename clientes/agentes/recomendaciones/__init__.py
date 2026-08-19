"""Área `recomendaciones` de Clientes — Recomendaciones.

Contesta: ¿Qué más me puede servir?
Entidad:  cliente × catálogo

    NO EXPONE (y no puede: el código no mapea esos campos):
      (no aplica)

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Clientes importa código de
Vendedores.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      - `productos` — para el catálogo
"""
from clientes.agentes.recomendaciones.agente import NODO
from clientes.agentes.recomendaciones.tools import TOOLS

# razona sobre historial para sugerir
MODELO = "claude-sonnet-5"

# lookup contra el backend, responde en segundos
# Su cola propia. La consume SU servicio, nadie más.
COLA = "c:recomendaciones"

__all__ = ["MODELO", "COLA", "NODO", "TOOLS"]
