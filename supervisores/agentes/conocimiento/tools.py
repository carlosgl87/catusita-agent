"""Tools de `conocimiento` (supervisores). El orquestador NO ve la búsqueda por dentro."""
from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


@tool
async def buscar_conocimiento(
    consulta: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Busca en los procesos de Catusita cómo se resuelve algo. Úsala cuando lo
    que te sirvió el contexto no alcance, o cuando la consulta no corresponda a
    ninguna otra área. Pasa la consulta del usuario TAL CUAL, sin reformularla."""
    raise NotImplementedError


@tool
async def solicitar_proceso_nuevo(
    consulta: str,
    motivo: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Deja registrado que falta un procedimiento. Úsala cuando el proceso que
    recuperaste NO resuelve lo que están preguntando: mejor decir que no lo
    tienes y que quede anotado, que inventar un procedimiento. En `motivo`,
    por qué no servía lo que encontraste."""
    raise NotImplementedError


TOOLS = [buscar_conocimiento, solicitar_proceso_nuevo]

# ── Los dos orígenes de una solicitud ────────────────────────────────────────
#
#   'sin_resultado'   automático. `contexto` buscó y no pasó el UMBRAL. Lo
#                     registra el área sola al no encontrar nada.
#
#   'rechazado'       deliberado. Esta tool. SÍ había un proceso pero al
#                     orquestador no le servía. Es la señal más valiosa: hay un
#                     procedimiento que PARECE aplicar y no aplica, y eso no se
#                     arregla escribiendo uno nuevo sino corrigiendo su `cuando`.
#
# Por eso `motivo` es obligatorio acá y NULL en el automático: en el primer caso
# no hay nada que explicar, en el segundo es todo lo que hay que explicar.
