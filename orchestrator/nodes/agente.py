"""Nodo 'agente': llama a Claude con las tools del canal y agrega el AIMessage al estado."""
import os
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

from orchestrator.graph_state import AgentState
from orchestrator.lc_tools import TOOLS_VENDEDOR_LC, TOOLS_CLIENTE_LC
from orchestrator.prompts import SYSTEM_VENDEDOR, SYSTEM_CLIENTE

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Dos modelos pre-bindeados para evitar re-bindear en cada llamada.
# Se crean lazy al primer uso del nodo.
_bound: dict = {}


def _get_bound(canal: str, perfil: dict) -> ChatAnthropic:
    if canal not in _bound:
        tools = TOOLS_VENDEDOR_LC if canal == "vendedor" else TOOLS_CLIENTE_LC
        _bound[canal] = ChatAnthropic(model=_MODEL, max_tokens=2048).bind_tools(tools)
    return _bound[canal]


async def nodo_agente(state: AgentState) -> dict:
    canal = state.get("canal", "vendedor")
    perfil = state.get("perfil", {})

    if canal == "vendedor":
        system_text = SYSTEM_VENDEDOR.format(
            nombre=perfil.get("nombre", "Asesor"),
            linea_asignada=perfil.get("linea_asignada", "general"),
            vendedor_id=perfil.get("vendedor_id", "V001"),
        )
    else:
        system_text = SYSTEM_CLIENTE

    messages = [SystemMessage(content=system_text)] + list(state["messages"])
    model = _get_bound(canal, perfil)
    response = await model.ainvoke(messages)
    return {"messages": [response]}
