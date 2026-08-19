"""Área `clientes` de Vendedores.

Contesta: ¿Quién es este cliente y está en mi cartera?

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `backend`, `servicio`,
`prompt` ni `agente` desde afuera.

No le habla a ninguna otra área. Si le falta un dato, vuelve al orquestador.
"""
from vendedores.agentes.clientes.agente import NODO, MODELO
from vendedores.agentes.clientes.tools import TOOLS

# Lo que el orquestador ve de esta área. Es la PREGUNTA que contesta, no
# la lista de sus tools: el orquestador delega en el área y es ella la que
# decide cuáles usar y en qué orden.
DESCRIPCION = (
    "Quién es un cliente y si está en la cartera del asesor. También la lista completa de su cartera."
)

__all__ = ["MODELO", "DESCRIPCION", "NODO", "TOOLS"]
