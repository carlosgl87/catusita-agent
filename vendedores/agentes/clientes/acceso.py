"""Control de acceso por cartera. Vive acá porque `clientes` es dueño del dato.

NO es un handoff: es código determinista que corre siempre, antes de la tool.
Otras áreas de vendedores lo importan directo. Única dependencia de código
permitida entre áreas, y en un solo sentido.

TODO: migrar desde orchestrator/access.py.
"""


async def verificar_cartera(ruc: str, perfil: dict) -> dict | None:
    """None si puede consultarlo; dict de error si el RUC no es de su cartera."""
    raise NotImplementedError
