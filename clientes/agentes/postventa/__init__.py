"""Área `postventa` de Clientes — Postventa.

Contesta: Quiero reclamar o devolver algo.
Entidad:  reclamo

    NO EXPONE (y no puede: el código no mapea esos campos):
      (no aplica)

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Clientes importa código de
Vendedores.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      (se basta con lo suyo)
"""
from clientes.agentes.postventa.agente import NODO
from clientes.agentes.postventa.tools import TOOLS

# captura estructurada de datos
MODELO = "claude-haiku-4-5-20251001"

# lookup contra el backend, responde en segundos
# Su cola propia. La consume SU servicio, nadie más.
COLA = "c:postventa"

__all__ = ["MODELO", "COLA", "NODO", "TOOLS"]
