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

# Lo que el orquestador ve de esta área. Es la PREGUNTA que contesta, no
# la lista de sus tools: el orquestador delega en el ÁREA y es ella la que
# decide cuáles usar y en qué orden.
DESCRIPCION = (
    "Reclamos, devoluciones y garantías sobre algo que el cliente ya compró."
)

__all__ = ["MODELO", "DESCRIPCION", "NODO", "TOOLS"]
