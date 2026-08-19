"""Área `productos` de Clientes — Productos.

Contesta: ¿Tienen esta pieza y cuánto cuesta?
Entidad:  SKU

    NO EXPONE (y no puede: el código no mapea esos campos):
      - precio_neto y descuentos — este backend NO mapea ese campo
      - almacén y ubicación física — tampoco se mapea

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Clientes importa código de
Vendedores.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      (se basta con lo suyo)
"""
from clientes.agentes.productos.agente import NODO
from clientes.agentes.productos.tools import TOOLS

# búsqueda dirigida sobre datos
MODELO = "claude-haiku-4-5-20251001"

# lookup contra el backend, responde en segundos
# Su cola propia. La consume SU servicio, nadie más.
COLA = "c:productos"

__all__ = ["MODELO", "COLA", "NODO", "TOOLS"]
