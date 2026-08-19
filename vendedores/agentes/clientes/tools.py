"""Tools internas de `clientes` (vendedores). El orquestador NO las ve.

    Código a migrar:
      - agents/cartera.py
      - orchestrator/access.py -> acceso.py
"""
from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
async def consultar_cartera(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Clientes de la cartera del asesor."""
    raise NotImplementedError


@tool
async def consultar_perfil_cliente(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Ficha de un cliente de la cartera, por RUC."""
    raise NotImplementedError


TOOLS = [consultar_cartera, consultar_perfil_cliente]
