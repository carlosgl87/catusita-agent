"""Área `pedidos` de Vendedores — Pedidos y despacho.

Contesta: ¿Dónde está el pedido y ya llegó?
Entidad:  pedido / factura

    EXPONE datos sensibles:
      - pedidos de cualquier cliente de la cartera

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Vendedores importa código de
Clientes.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      (se basta con lo suyo)
"""
from vendedores.agentes.pedidos.agente import NODO
from vendedores.agentes.pedidos.tools import TOOLS

# encadena dos consultas deterministas
MODELO = "claude-haiku-4-5-20251001"

# lookup contra el backend, responde en segundos
# Su cola propia. La consume SU servicio, nadie más.
COLA = "v:pedidos"

__all__ = ["MODELO", "COLA", "NODO", "TOOLS"]
