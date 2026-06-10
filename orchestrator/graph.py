"""Grafo LangGraph del agente Catusita (equivalente 1:1 al run_agent actual).

Topología mínima (Fase 2):
  START → agente ──(tool_calls?)──► tools ──► agente
                └──(no)──► END

Fases siguientes agregan nodos pre_resolver (Fase 4) y validar (Fase 5).
"""
from langchain_core.messages import HumanMessage, AIMessage

from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from orchestrator.graph_state import AgentState
from orchestrator.nodes.agente import nodo_agente
from orchestrator.lc_tools import TOOLS_VENDEDOR_LC, TOOLS_CLIENTE_LC


def _build_graph() -> StateGraph:
    # Todos los tools en una lista deduplicada para que ToolNode los encuentre.
    # El nodo agente filtra qué subset bindea según el canal.
    all_tools = list({t.name: t for t in TOOLS_VENDEDOR_LC + TOOLS_CLIENTE_LC}.values())
    tool_node = ToolNode(all_tools)

    g = StateGraph(AgentState)
    g.add_node("agente", nodo_agente)
    g.add_node("tools", tool_node)

    g.set_entry_point("agente")
    g.add_conditional_edges("agente", tools_condition)
    g.add_edge("tools", "agente")

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


async def run_agent_graph(mensaje: str, perfil: dict, historial: list) -> str:
    """Equivalente a router.run_agent pero usando el grafo LangGraph.

    Mismo contrato: recibe mensaje, perfil y historial (formato Redis),
    devuelve la respuesta final como string.
    """
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

    final = await graph.ainvoke(state)

    # El último mensaje es la respuesta final del agente
    for msg in reversed(final["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content if isinstance(msg.content, str) else str(msg.content)

    return "No pude procesar tu consulta en este momento. Inténtalo de nuevo."
