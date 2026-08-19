"""Área `pedidos` de Vendedores.

Contesta: ¿Dónde está el pedido y ya llegó?

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `backend`, `servicio`,
`prompt` ni `agente` desde afuera.

No le habla a ninguna otra área. Si le falta un dato, vuelve al orquestador.
"""
from vendedores.agentes.pedidos.agente import NODO, MODELO
from vendedores.agentes.pedidos.tools import TOOLS

# Lo que el orquestador ve de esta área. Es la PREGUNTA que contesta, no
# la lista de sus tools: el orquestador delega en el área y es ella la que
# decide cuáles usar y en qué orden.
DESCRIPCION = (
    "Qué pidió un cliente y en qué va el despacho: estado, guía de remisión, si ya se entregó."
)

__all__ = ["MODELO", "DESCRIPCION", "NODO", "TOOLS"]
