"""Contratos de `recomendaciones` (clientes). Frontera del área: cliente × catálogo."""
from pydantic import BaseModel


class Resultado(BaseModel):
    """TODO: lo que esta área le devuelve al orquestador."""
