"""Tools internas de `vehiculos` (clientes). El orquestador NO las ve.

    Código a migrar:
      - agents/vehicle.py, recortando el mapeo
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
    """Marca, modelo, año y motor de una placa peruana."""
    raise NotImplementedError


TOOLS = [consultar_placa_sunarp]
