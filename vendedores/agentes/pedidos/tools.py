"""Tools internas de `pedidos` (vendedores). El orquestador NO las ve.

    Código a migrar:
      - agents/orders.py
"""
from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
async def consultar_pedidos(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Pedidos de un cliente por RUC, con factura y despacho."""
    raise NotImplementedError


@tool
async def consultar_despacho(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Estado de entrega: guía y fechas."""
    raise NotImplementedError


TOOLS = [consultar_pedidos, consultar_despacho]
