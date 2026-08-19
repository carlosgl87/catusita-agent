"""Tools internas de `productos` (clientes). El orquestador NO las ve.

    Código a migrar:
      - agents/stock.py, agents/prices.py (solo tipo='lista'), agents/imagenes.py
"""
from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
async def consultar_stock(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Si hay o no disponibilidad. Sin decir en qué almacén."""
    raise NotImplementedError


@tool
async def consultar_precio(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Precio de lista. Nada más."""
    raise NotImplementedError


@tool
async def enviar_imagen_producto(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Envía por WhatsApp la foto de un producto."""
    raise NotImplementedError


@tool
async def buscar_catalogo(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Busca productos por descripción o síntoma."""
    raise NotImplementedError


TOOLS = [consultar_stock, consultar_precio, enviar_imagen_producto, buscar_catalogo]
