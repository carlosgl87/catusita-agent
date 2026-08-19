"""Tools de `clientes` (vendedores): quién es este cliente y es mío.

Las dos son sensibles: devuelven límite de crédito, saldo y último pedido. Por
eso `consultar_perfil_cliente` pasa por el control de cartera ANTES de tocar el
backend — nunca al revés. Consultar primero y filtrar después significa que el
dato ajeno ya salió.

`consultar_cartera` no lo necesita: solo puede devolver lo del asesor que
pregunta, porque el vendedor_id sale de su perfil y no de un argumento.
"""
import json
from typing import Annotated, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from vendedores.agentes.clientes import backend
from vendedores.plataforma_vendedores import acceso


def _responder(resultado: dict, tool_call_id: str) -> Command:
    return Command(update={"messages": [ToolMessage(
        content=json.dumps(resultado, ensure_ascii=False, default=str),
        tool_call_id=tool_call_id)]})


@tool
async def consultar_cartera(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
) -> Command:
    """Todos los clientes asignados a este asesor, con razón social, tipo,
    estado, límite de crédito, saldo pendiente y último pedido.

    Usar SIEMPRE que pregunten por «mis clientes», «mi cartera», «qué clientes
    tengo». Nunca contestar eso de memoria.

    `estado`: activo | suspendido | bloqueado
    `tipo`:   taller | distribuidor | consumidor_final"""
    vendedor_id = (state.get("perfil") or {}).get("vendedor_id")
    if not vendedor_id:
        return _responder({
            "error": "SIN_VENDEDOR",
            "mensaje": "No se pudo identificar al asesor.",
        }, tool_call_id)
    return _responder(await backend.cartera(vendedor_id, estado, tipo), tool_call_id)


@tool
async def consultar_perfil_cliente(
    cliente: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Perfil de UN cliente: razón social, dirección, teléfono, tipo, asesor
    asignado y estado.

    `cliente` puede ser el RUC o el nombre — se resuelve dentro de la cartera
    del asesor. Si el cliente no es suyo, la consulta no se ejecuta."""
    perfil_asesor = state.get("perfil") or {}
    ruc, error = await acceso.verificar(cliente, perfil_asesor)
    if error:
        return _responder(error, tool_call_id)
    return _responder(await backend.perfil(ruc), tool_call_id)


TOOLS = [consultar_cartera, consultar_perfil_cliente]
