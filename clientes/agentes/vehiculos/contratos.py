"""Contratos de `vehiculos` (clientes). Frontera del área: placa / VIN."""
from pydantic import BaseModel


class Resultado(BaseModel):
    """TODO: lo que esta área le devuelve al orquestador."""
