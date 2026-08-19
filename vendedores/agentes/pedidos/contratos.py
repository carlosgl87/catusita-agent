"""Contratos de `pedidos` (vendedores). Frontera del área: pedido / factura."""
from pydantic import BaseModel


class Resultado(BaseModel):
    """TODO: lo que esta área le devuelve al orquestador."""
