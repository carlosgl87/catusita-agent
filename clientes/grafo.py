"""Grafo de Clientes.

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
import os

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import tools_condition

from plataforma.estado import EstadoAgente
from plataforma.nodos.contexto import hacer_nodo_contexto
from plataforma.nodos.validar import hacer_nodo_validar, MAX_REINTENTOS
from clientes import registro
from clientes.orquestador import nodo_orquestador

RECURSION_LIMIT = int(os.getenv("LANGGRAPH_RECURSION_LIMIT", "20"))


def _routing_validar(state) -> str:
    val = state.get("validacion") or {}
    if val.get("ok") is False and state.get("intentos_validacion", 0) <= MAX_REINTENTOS:
        return "orquestador"
    return END


def construir():
    g = StateGraph(EstadoAgente)
    g.add_node("contexto", hacer_nodo_contexto("clientes"))
    g.add_node("orquestador", nodo_orquestador)
    g.add_node("validar", hacer_nodo_validar("clientes"))

    g.set_entry_point("contexto")
    g.add_edge("contexto", "orquestador")

    areas = registro.nodos()
    for nombre, subgrafo in areas.items():
        g.add_node(nombre, subgrafo)
        g.add_edge(nombre, "orquestador")   # única salida

    g.add_conditional_edges(
        "orquestador", tools_condition, {**{n: n for n in areas}, END: "validar"}
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
        if e.source in areas:
            if e.target in areas:
                fallos.append(f"{e.source} -> {e.target}: las áreas no se hablan entre sí")
            elif e.target != "orquestador":
                fallos.append(f"{e.source} -> {e.target}: solo puede volver al orquestador")
    return fallos


# TODO: grafo = construir().compile()
