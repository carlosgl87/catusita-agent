"""Tools internas de `recomendaciones` (clientes). El orquestador NO las ve.

    Código a migrar:
      (nueva)
"""
from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
async def recomendar_productos(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Sugiere productos relacionados o complementarios."""
    raise NotImplementedError


TOOLS = [recomendar_productos]
