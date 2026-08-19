"""Contratos de `conocimiento`."""
from pydantic import BaseModel


class Proceso(BaseModel):
    """Un procedimiento recuperado. Trae el cómo Y el cómo se entrega."""
    titulo: str
    cuando: str            # la situación en que aplica (es lo que se embebe)
    pasos: str             # cómo se resuelve
    entrega: str | None    # cómo se le presenta al usuario
    similitud: float
