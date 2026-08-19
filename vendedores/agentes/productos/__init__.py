"""Área `productos` de Vendedores — Productos.

Contesta: ¿Qué pieza es, existe, cuánto vale y cómo se ve?
Entidad:  SKU

    EXPONE datos sensibles:
      - precio neto y escala de descuentos
      - stock desglosado por almacén

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Vendedores importa código de
Clientes.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      (se basta con lo suyo)
"""
from vendedores.agentes.productos.agente import NODO
from vendedores.agentes.productos.tools import TOOLS

# búsqueda dirigida sobre datos
MODELO = "claude-haiku-4-5-20251001"

# lookup contra el backend, responde en segundos
# Su cola propia. La consume SU servicio, nadie más.
COLA = "v:productos"

__all__ = ["MODELO", "COLA", "NODO", "TOOLS"]
