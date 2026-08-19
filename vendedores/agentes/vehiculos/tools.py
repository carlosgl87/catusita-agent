"""Tools internas de `vehiculos` (vendedores). El orquestador NO las ve.

    Código a migrar:
      - agents/vehicle.py
      - agents/yahuar_subagente.py + shared/yahuar.py
"""
from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
async def consultar_placa_sunarp(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Consulta oficial SUNARP por placa. Tarda 20-60s."""
    raise NotImplementedError


@tool
async def consultar_placa_yahuar(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Consulta la placa por el relay de WhatsApp de Yahuar."""
    raise NotImplementedError


TOOLS = [consultar_placa_sunarp, consultar_placa_yahuar]
