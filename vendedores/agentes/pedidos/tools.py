"""Tools de `pedidos` (vendedores): qué pidió un cliente y dónde está."""
import json
from typing import Annotated, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from vendedores.agentes.pedidos import backend
from vendedores.plataforma_vendedores import acceso


def _responder(resultado: dict, tool_call_id: str) -> Command:
    return Command(update={"messages": [ToolMessage(
        content=json.dumps(resultado, ensure_ascii=False, default=str),
        tool_call_id=tool_call_id)]})


@tool
async def consultar_pedidos(
    cliente: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    estado: Optional[str] = None,
) -> Command:
    """Pedidos de un cliente: estado, N° de factura SUNAT, estado de despacho y
    notas de crédito.

    `cliente` puede ser el RUC o el nombre — se resuelve dentro de la cartera
    del asesor. La búsqueda es POR CLIENTE, no por número de pedido."""
    ruc, error = await acceso.verificar(cliente, state.get("perfil") or {})
    if error:
        return _responder(error, tool_call_id)
    return _responder(await backend.pedidos(ruc, estado), tool_call_id)


@tool
async def consultar_despacho(
    tool_call_id: Annotated[str, InjectedToolCallId],
    pedido_id: Optional[str] = None,
    factura: Optional[str] = None,
) -> Command:
    """Si un pedido ya se entregó: guía de remisión, fecha de despacho y de
    entrega. Para «¿ya llegó?», «¿se entregó?», «¿en qué va el despacho?».

    NO funciona por RUC. Necesita el N° de pedido o el de factura: si solo
    tenés el cliente, usá consultar_pedidos primero para sacar sus números."""
    if not pedido_id and not factura:
        return _responder({
            "error": "FALTA_DATO",
            "mensaje": ("Se necesita el número de pedido o el de factura. "
                        "Con el RUC no alcanza: usá consultar_pedidos primero."),
        }, tool_call_id)
    return _responder(await backend.despacho(pedido_id, factura), tool_call_id)


TOOLS = [consultar_pedidos, consultar_despacho]
