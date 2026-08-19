"""Contratos de `productos` (vendedores). Frontera del área: el SKU.

Estos modelos NO se serializan hacia el orquestador — el área le deja los
resultados crudos en `messages` para que los vea tal como salieron del backend.
Sirven para validar en los tests que el backend sigue devolviendo lo que el
área espera, que es donde un cambio del Mock SAP rompería en silencio.
"""
from pydantic import BaseModel


class Stock(BaseModel):
    sku: str
    total: int
    por_almacen: dict[str, int] = {}


class Precio(BaseModel):
    sku: str
    moneda: str = "PEN"
    # Solo vendedores. El área de clientes no tiene este campo en su contrato.
    neto: float | None = None
    lista: float | None = None


class ProductoCatalogo(BaseModel):
    sku: str
    nombre: str
    categoria: str | None = None
    marca: str | None = None


class Sugerencias(BaseModel):
    """Lo que devuelve el fallback cuando el SKU no existe.

    Es un error con salida: el orquestador puede repreguntar en vez de cortar
    la conversación con «no lo encontré».
    """
    error: str
    mensaje: str
    sugerencias: list[ProductoCatalogo]
