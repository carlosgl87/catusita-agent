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
from clientes.agentes.productos.agente import NODO, MODELO
from clientes.agentes.productos.tools import TOOLS


# lookup contra el backend, responde en segundos

# Lo que el orquestador ve de esta área. Es la PREGUNTA que contesta, no
# la lista de sus tools: el orquestador delega en el ÁREA y es ella la que
# decide cuáles usar y en qué orden.
DESCRIPCION = (
    "Si tenemos una pieza, cuánto cuesta y cómo se ve. Catálogo, disponibilidad, precio de lista y fotos de producto."
)

__all__ = ["MODELO", "DESCRIPCION", "NODO", "TOOLS"]
