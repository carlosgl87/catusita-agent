"""Descubrimiento de las áreas de Supervisores.

Recorre `supervisores/agentes/*/` y lee su contrato público. El orquestador de
este multiagente solo puede delegar en estas áreas: las de `clientes` no existen
para él, porque están en otro paquete y este registro nunca las mira.

── Por qué se descubren y no se listan ────────────────────────────────────────

Una lista central de áreas es un lugar más que actualizar al agregar una, y el
día que alguien se olvide, el área existe en el disco y no en el grafo — sin un
solo error. Acá el contrato es la lista: si la carpeta declara MODELO, TOOLS y
DESCRIPCION, entra.
"""
import importlib
import logging
import pkgutil
from pathlib import Path

from langchain_core.tools import tool

_PAQUETE = "supervisores.agentes"
_DIR = Path(__file__).parent / "agentes"
_REQUERIDO = ("MODELO", "TOOLS", "DESCRIPCION")


def _descubrir() -> dict:
    areas = {}
    for info in pkgutil.iter_modules([str(_DIR)]):
        if not info.ispkg:
            continue
        try:
            mod = importlib.import_module(f"{_PAQUETE}.{info.name}")
        except Exception as e:
            logging.error(f"[supervisores] área {info.name!r} no importa: {e}")
            continue
        if faltan := [c for c in _REQUERIDO if not hasattr(mod, c)]:
            logging.warning(
                f"[supervisores] área {info.name!r} sin {faltan}, ignorada.")
            continue
        areas[info.name] = mod
    return areas


_AREAS = _descubrir()


def nodos() -> dict:
    """{nombre: subgrafo}. Solo las que tienen NODO compilado."""
    return {n: m.NODO for n, m in _AREAS.items() if getattr(m, "NODO", None) is not None}


def tools_de_delegacion() -> list:
    """Una tool por área, para que el orquestador delegue.

    ── Qué ve el orquestador ──────────────────────────────────────────────────

    Una tool por área, descrita por la PREGUNTA que contesta. No ve
    `consultar_stock` ni `enviar_documento`: eso es de adentro del área y es
    ella la que decide cuáles usar.

    Es la diferencia con el diseño anterior, donde el orquestador tenía todas
    las tools sueltas y elegía entre ellas. Con áreas elige entre un puñado de
    cosas que se leen como preguntas de negocio.

    ── Cómo salta ─────────────────────────────────────────────────────────────

    `Command(goto=<area>)`: un salto EN MEMORIA dentro del mismo proceso, no un
    mensaje por Redis. Sin `graph=PARENT` porque estas tools las ejecuta un
    ToolNode del MISMO grafo donde viven las áreas.

    ── Estas tools NUNCA se ejecutan ──────────────────────────────────────────

    Existen solo para que el modelo del orquestador conozca el esquema: qué
    áreas hay, qué contesta cada una y que hay que mandarle una `consulta`.

    Quien hace el salto es el nodo `delegar` de `supervisores/grafo.py`, que lee
    la tool_call elegida y devuelve `Command(goto=<área>)`. Y quien responde el
    `tool_use` es el ÁREA, con su resultado adentro.

    No pasa por un ToolNode a propósito: ToolNode exige que la tool devuelva su
    propio ToolMessage en el mismo paso, y acá el resultado recién existe cuando
    el área termina de trabajar.

    ── Por qué el área no comparte la conversación ────────────────────────────

    La primera versión dejaba que el área escribiera en el mismo `messages` del
    orquestador. La conversación terminaba en un AIMessage del área y Anthropic
    la rechazaba: «the conversation must end with a user message». Dos modelos
    escribiendo en la misma lista no funciona.
    """
    hechas = []
    for nombre, mod in sorted(_AREAS.items()):
        if getattr(mod, "NODO", None) is None:
            # Un área sin subgrafo no se puede delegar. Se omite en vez de
            # ofrecerla y fallar al saltar.
            logging.warning(f"[supervisores] área {nombre!r} sin NODO, no se delega.")
            continue
        hechas.append(_hacer_tool(nombre, mod.DESCRIPCION))
    return hechas


def _hacer_tool(nombre: str, descripcion: str):
    """Cierra sobre el nombre del área. En una función aparte porque hacerlo
    dentro del for capturaría la última iteración en todas."""

    @tool(f"consultar_{nombre}", description=descripcion)
    def _delegar(consulta: str) -> str:
        """`consulta`: qué necesitás del área, en una frase. El área NO ve la
        conversación, solo esto. Si le mandás «el stock» sin decir de qué, no
        tiene con qué trabajar.

        Nunca se ejecuta: el salto lo hace el nodo `delegar` del grafo."""
        return ""

    return _delegar


def mapa() -> dict:
    """{area: (modelo, [tools])}. Para logs y diagnóstico."""
    return {n: (m.MODELO, [t.name for t in m.TOOLS]) for n, m in _AREAS.items()}


def area_de_tool(tool_name: str) -> str:
    """`consultar_productos` -> `productos`. Vacío si no es una delegación."""
    nombre = (tool_name or "").removeprefix("consultar_")
    return nombre if nombre in _AREAS else ""
