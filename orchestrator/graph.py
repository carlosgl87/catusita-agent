"""Grafo LangGraph del agente Catusita.

Topología completa (Fases 2-5):
  START → pre_resolver → agente ──(tool_calls?)──► tools ──► agente
                              └──(no)──► validar ──(ok)──► END
                                             └──(falla, quedan intentos)──► agente
"""
from langchain_core.messages import HumanMessage, AIMessage

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from orchestrator.graph_state import AgentState
from orchestrator.nodes.agente import nodo_agente
from orchestrator.nodes.pre_resolver import nodo_pre_resolver
from orchestrator.nodes.validar import nodo_validar, MAX_REINTENTOS
from orchestrator.lc_tools import TOOLS_VENDEDOR_LC, TOOLS_CLIENTE_LC


def _routing_validar(state: AgentState) -> str:
    """Decide si la validación pasó (→ END) o debe reintentar (→ agente)."""
    val = state.get("validacion") or {}
    intentos = state.get("intentos_validacion", 0)
    if val.get("ok") is False and intentos <= MAX_REINTENTOS:
        return "agente"
    return END


def _build_graph() -> StateGraph:
    all_tools = list({t.name: t for t in TOOLS_VENDEDOR_LC + TOOLS_CLIENTE_LC}.values())
    tool_node = ToolNode(all_tools)

    g = StateGraph(AgentState)
    g.add_node("pre_resolver", nodo_pre_resolver)
    g.add_node("agente", nodo_agente)
    g.add_node("tools", tool_node)
    g.add_node("validar", nodo_validar)

    g.set_entry_point("pre_resolver")
    g.add_edge("pre_resolver", "agente")
    g.add_conditional_edges("agente", tools_condition, {"tools": "tools", END: "validar"})
    g.add_edge("tools", "agente")
    g.add_conditional_edges("validar", _routing_validar, {"agente": "agente", END: END})

    return g


graph = _build_graph().compile()


def _historial_a_lc(historial: list) -> list:
    """Convierte historial de Redis [{role, content}] a mensajes LangChain."""
    lc = []
    for m in historial:
        role, content = m.get("role"), m.get("content", "")
        if role == "user":
            lc.append(HumanMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
    return lc


async def _invoke(mensaje: str, perfil: dict, historial: list) -> dict:
    """Invoca el grafo y devuelve el estado final completo."""
    canal = "vendedor" if perfil.get("tipo") == "asesor" else "cliente"
    mensajes_lc = _historial_a_lc(historial) + [HumanMessage(content=mensaje)]

    state: AgentState = {
        "messages": mensajes_lc,
        "perfil": perfil,
        "canal": canal,
        "media_pendiente": [],
        "contexto_resuelto": {},
        "validacion": {},
        "intentos_validacion": 0,
    }
    return await graph.ainvoke(state)


def _extraer_respuesta(final: dict) -> str:
    for msg in reversed(final["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return "No pude procesar tu consulta en este momento. Inténtalo de nuevo."


async def run_agent_graph(mensaje: str, perfil: dict, historial: list) -> str:
    """Equivalente a router.run_agent. Devuelve la respuesta como string."""
    final = await _invoke(mensaje, perfil, historial)
    return _extraer_respuesta(final)


async def run_agent_graph_full(
    mensaje: str, perfil: dict, historial: list
) -> tuple[str, list]:
    """Como run_agent_graph pero también devuelve la lista media_pendiente.

    Usado por el webhook para enviar imágenes (ej. tarjeta SUNARP) por WhatsApp.
    Returns: (respuesta_texto, media_pendiente)
    """
    final = await _invoke(mensaje, perfil, historial)
    respuesta = _extraer_respuesta(final)
    media = final.get("media_pendiente") or []
    return respuesta, media
