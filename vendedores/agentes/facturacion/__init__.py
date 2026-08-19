"""Área `facturacion` de Vendedores.

Contesta: ¿Está pagada? Mandame el PDF.

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `backend`, `servicio`,
`prompt` ni `agente` desde afuera.

No le habla a ninguna otra área. Si le falta un dato, vuelve al orquestador.
"""
from vendedores.agentes.facturacion.agente import NODO, MODELO
from vendedores.agentes.facturacion.tools import TOOLS

# Lo que el orquestador ve de esta área. Es la PREGUNTA que contesta, no
# la lista de sus tools: el orquestador delega en el área y es ella la que
# decide cuáles usar y en qué orden.
DESCRIPCION = (
    "Facturas y notas de crédito: bajar el PDF, o saber si están pagadas y cómo."
)

__all__ = ["MODELO", "DESCRIPCION", "NODO", "TOOLS"]
