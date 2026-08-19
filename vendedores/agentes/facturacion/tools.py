"""Tools internas de `facturacion` (vendedores). El orquestador NO las ve.

    Código a migrar:
      - agents/documents.py
"""
from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
async def enviar_documento(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Envía el PDF de una factura o nota de crédito."""
    raise NotImplementedError


@tool
async def consultar_pago_documento(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Estado de pago: letras, NC y saldo."""
    raise NotImplementedError


TOOLS = [enviar_documento, consultar_pago_documento]
