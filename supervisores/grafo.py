"""Grafo de Supervisores.

    (entra del router) -> contexto -> supervisor -> validar -> respuesta
                                        |    ^
                                        v    |
                                     (un área)

El orquestador es el único que coordina. Las áreas no se hablan entre sí: si a
un área le falta un dato de otra, vuelve al orquestador diciendo qué necesita.

Se fuerza acá, en el constructor:
  - de cada área sale UNA arista, y va a `supervisor`
  - ningún área tiene arista a otra área
  - ningún área tiene arista a END  (si no, se saltaría `validar`)
"""
import logging
import os

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import tools_condition
from langgraph.types import Command

from supervisores.plataforma_supervisores.estado import EstadoAgente
from supervisores.plataforma_supervisores.nodos.contexto import nodo_contexto
from supervisores.plataforma_supervisores.nodos.validar import nodo_validar, MAX_REINTENTOS
from supervisores import registro
from supervisores.orquestador import nodo_orquestador

RECURSION_LIMIT = int(os.getenv("LANGGRAPH_RECURSION_LIMIT", "20"))


async def _nodo_delegar(state):
    """Lee a qué área quiso ir el orquestador y salta.

    No es un ToolNode. ToolNode exige que la tool devuelva su propio ToolMessage
    en el mismo paso, y acá el resultado recién existe cuando el área terminó de
    trabajar — puede tardar un minuto. Quien responde el `tool_use` es el área.

    Si el orquestador pidió varias áreas de una, se atiende la PRIMERA y las
    demás quedan sin responder. Eso rompería la conversación, así que el prompt
    le pide una por vez; acá se registra si igual manda varias.
    """
    ultimo = state["messages"][-1]
    llamadas = getattr(ultimo, "tool_calls", None) or []
    if not llamadas:
        return Command(goto="orquestador")

    if len(llamadas) > 1:
        logging.warning(
            f"[delegar] el orquestador pidió {len(llamadas)} áreas de una: "
            f"{[c.get('name') for c in llamadas]}. Se atiende la primera."
        )

    llamada = llamadas[0]
    area = registro.area_de_tool(llamada.get("name", ""))
    if not area:
        return Command(goto="orquestador")

    return Command(goto=area, update={"encargo": {
        "consulta": (llamada.get("args") or {}).get("consulta", ""),
        "tool_call_id": llamada.get("id", ""),
    }})


def _envolver_area(nombre: str, subgrafo):
    """Convierte un subgrafo de área en un nodo del grafo del multiagente.

    ── Por qué el área NO comparte `messages` con el orquestador ──────────────

    Porque son dos modelos distintos escribiendo en la misma conversación. El
    área termina su loop con un AIMessage propio, y entonces lo que el
    orquestador manda a Anthropic termina en un mensaje de assistant:

        "This model does not support assistant message prefill.
         The conversation must end with a user message."

    Además el área vería el historial completo y las respuestas de las otras
    áreas — contexto que no necesita y que le cuesta tokens en cada llamada.

    Así que el área arranca limpia: una sola consulta, la que el orquestador
    escribió al delegar. Lo que sabe hacer no depende de lo que se dijo antes.

    ── Qué devuelve ───────────────────────────────────────────────────────────

    Un ToolMessage contra el `tool_call_id` de la delegación, con su resultado
    adentro. Para el orquestador, delegar en un área se ve igual que llamar a
    una tool: pide algo y le vuelve el resultado.

    Y `media_pendiente`, que tiene reducer de suma: si dos áreas del mismo turno
    encolan archivos, salen los dos.
    """

    async def _nodo(state):
        encargo = state.get("encargo") or {}
        consulta = encargo.get("consulta") or ""
        tool_call_id = encargo.get("tool_call_id") or ""

        salida = await subgrafo.ainvoke({
            **state,
            "messages": [HumanMessage(content=consulta)],
        })

        respuesta = ""
        for m in reversed(salida.get("messages") or []):
            if isinstance(m, AIMessage) and m.content:
                respuesta = m.content if isinstance(m.content, str) else str(m.content)
                break

        return {
            "messages": [ToolMessage(
                content=respuesta or f"{nombre} no devolvió resultado.",
                tool_call_id=tool_call_id,
            )],
            "media_pendiente": salida.get("media_pendiente") or [],
        }

    return _nodo


def _routing_validar(state) -> str:
    val = state.get("validacion") or {}
    if val.get("ok") is False and state.get("intentos_validacion", 0) <= MAX_REINTENTOS:
        return "orquestador"
    return END


def construir():
    g = StateGraph(EstadoAgente)
    g.add_node("contexto", nodo_contexto)
    g.add_node("orquestador", nodo_orquestador)
    g.add_node("validar", nodo_validar)

    g.set_entry_point("contexto")
    g.add_edge("contexto", "orquestador")

    areas = registro.nodos()
    for nombre, subgrafo in areas.items():
        g.add_node(nombre, _envolver_area(nombre, subgrafo))
        g.add_edge(nombre, "orquestador")   # única salida

    # `delegar` ejecuta la tool que eligió el orquestador. Esa tool devuelve un
    # Command(goto=<área>), así que este nodo no tiene aristas de salida
    # declaradas: el destino lo decide el Command en tiempo de ejecución.
    #
    # Hace falta un nodo y no basta una arista condicional porque la API de
    # Anthropic exige un `tool_result` por cada `tool_use`. Saltar directo al
    # área dejaría el tool_use sin respuesta y la llamada siguiente fallaría.
    g.add_node("delegar", _nodo_delegar)
    g.add_conditional_edges(
        "orquestador", tools_condition, {"tools": "delegar", END: "validar"}
    )
    g.add_conditional_edges(
        "validar", _routing_validar, {"orquestador": "orquestador", END: END}
    )
    return g


def verificar_topologia(compilado) -> list:
    """Violaciones de las reglas de salida. Vacío = correcto. Corre en los tests."""
    areas = set(registro.nodos())
    fallos = []
    for e in compilado.get_graph().edges:
        # `delegar` es infraestructura, no un área: salta a donde diga el Command.
        if e.source in areas:
            if e.target in areas:
                fallos.append(f"{e.source} -> {e.target}: las áreas no se hablan entre sí")
            elif e.target != "orquestador":
                fallos.append(f"{e.source} -> {e.target}: solo puede volver al orquestador")
    return fallos


grafo = construir().compile()

# Se verifica al importar, no en un test que alguien puede no correr. Un área
# con arista a otra área rompe la regla central del diseño y tiene que impedir
# que el proceso arranque, no salir en un reporte.
if _fallos := verificar_topologia(grafo):
    raise RuntimeError("grafo de supervisores mal armado: " + " | ".join(_fallos))
