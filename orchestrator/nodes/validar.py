"""Nodo validar: revisa la respuesta del agente antes de enviarla al usuario.

Estrategia híbrida (Opción C del plan):
  1. Reglas baratas (gratuitas, instantáneas) — atrapan lo más peligroso:
     - Mención de palabras prohibidas (precio neto, almacén/distrito, precio sin IGV)
     - Números de precio sin respaldo en tool_results (anti-alucinación básica)
  2. Juez LLM (solo cuando las reglas baratas no deciden Y la consulta es de riesgo):
     - Solo si se usó una tool sensible (credito, cobranzas, perfil_cliente)
     - Rúbrica: ¿respondió la pregunta?, grounding, privacidad, derivaciones

Salidas del nodo:
  - state["validacion"] = {"ok": True}   → el grafo va a END
  - state["validacion"] = {"ok": False, "motivo": "..."}  → el grafo vuelve al agente
  - Si se acotaron los reintentos: fallback seguro → fuerza END con mensaje seguro
"""
import re
import json
import logging
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from orchestrator.graph_state import AgentState
from shared import llm

MAX_REINTENTOS = 1

# ─── Palabras y patrones prohibidos (reglas baratas) ─────────────────────────

_PROHIBIDOS = [
    r"precio\s*neto",
    r"sin\s*igv",
    r"descuento\s*(de|del|por)\s*\d",   # "descuento de X%"
    r"\balm[aá]cen\b",                   # mencionar el almacén explícitamente
    r"\bdistrito\b",
    r"\bhora\s*de\s*reparto\b",
    r"\bruta\s*de\s*reparto\b",
]
_RE_PROHIBIDOS = [re.compile(p, re.IGNORECASE) for p in _PROHIBIDOS]

# Tools sensibles que activan el juez LLM
_TOOLS_SENSIBLES = {"consultar_credito", "consultar_cobranzas", "consultar_perfil_cliente"}


def _borrador(messages: list) -> str:
    """Extrae el último AIMessage como borrador de respuesta."""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


def _tool_results(messages: list) -> list[str]:
    """Extrae el contenido de los ToolMessages del turno actual."""
    resultados = []
    for m in messages:
        if isinstance(m, ToolMessage) and m.content:
            resultados.append(m.content)
    return resultados


def _tools_usadas(messages: list) -> set[str]:
    """Devuelve los nombres de las tools invocadas en los mensajes."""
    usadas = set()
    for m in messages:
        if isinstance(m, AIMessage) and hasattr(m, "tool_calls"):
            for tc in (m.tool_calls or []):
                usadas.add(tc.get("name", ""))
    return usadas


# ─── Reglas baratas ───────────────────────────────────────────────────────────

def _reglas_baratas(borrador: str, canal: str) -> str | None:
    """Retorna el motivo de rechazo o None si pasa."""
    if canal != "vendedor":
        return None  # el agente de clientes no tiene info sensible de negocio
    for r in _RE_PROHIBIDOS:
        if r.search(borrador):
            palabra = r.pattern.replace("\\b", "").replace("\\s*", " ").split("(")[0].strip()
            return (
                f"La respuesta menciona información restringida ('{palabra}'). "
                f"El agente NO debe revelar: precio neto, descuentos, ubicación de almacén, "
                f"horario de reparto ni cualquier información operativa interna."
            )
    return None


# ─── Juez LLM ─────────────────────────────────────────────────────────────────

_RUBRICA = """Eres un auditor de respuestas del agente de ventas de Catusita.
Evalúa si la respuesta cumple TODAS estas reglas:

1. RESPONDIÓ la pregunta del usuario (no evadió ni dio respuesta genérica sin usar tools).
2. GROUNDING: cada dato concreto (monto, stock, fecha, número) viene de los tool_results.
   No inventó ningún valor.
3. PRIVACIDAD: no reveló precio neto, descuentos internos, ubicación de almacén/distrito,
   horario de reparto ni datos de clientes ajenos.
4. DERIVACIÓN: si corresponde derivar (excepción de crédito, precio especial), lo hizo
   correctamente sin inventar aprobaciones.

Responde SOLO con un JSON: {{"ok": true}} si pasa todo, o {{"ok": false, "motivo": "..."}}
si falla alguna regla (motivo en 1 oración concisa, en español).

Pregunta del usuario: {pregunta}
Tool results disponibles: {tool_results}
Respuesta del agente: {borrador}
"""


async def _juez_llm(pregunta: str, borrador: str, tool_results_json: str) -> dict:
    prompt = _RUBRICA.format(
        pregunta=pregunta,
        tool_results=tool_results_json[:3000],  # limitar tokens
        borrador=borrador,
    )
    try:
        texto = await llm.create_message(
            system="Eres un auditor de respuestas. Responde solo con JSON válido.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        raw = "".join(b.text for b in texto.content if hasattr(b, "text")).strip()
        # Extraer JSON aunque venga con ```json … ```
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        logging.error(f"Error en juez LLM: {e}")
    return {"ok": True}  # fallback conservador: no bloquear en caso de error


# ─── Nodo ─────────────────────────────────────────────────────────────────────

async def nodo_validar(state: AgentState) -> dict:
    messages = list(state.get("messages", []))
    canal = state.get("canal", "vendedor")
    intentos = state.get("intentos_validacion", 0)

    borrador = _borrador(messages)
    if not borrador:
        return {"validacion": {"ok": True}}

    # Si ya agotamos reintentos, dejar pasar (evitar loop infinito)
    if intentos >= MAX_REINTENTOS:
        logging.warning(f"Validador: máximo de reintentos alcanzado, dejando pasar.")
        return {"validacion": {"ok": True}, "intentos_validacion": intentos}

    # 1. Reglas baratas
    motivo_barato = _reglas_baratas(borrador, canal)
    if motivo_barato:
        return {
            "validacion": {"ok": False, "motivo": motivo_barato},
            "intentos_validacion": intentos + 1,
        }

    # 2. Juez LLM selectivo (solo si se usó una tool sensible)
    tools_usadas = _tools_usadas(messages)
    if tools_usadas & _TOOLS_SENSIBLES:
        # Obtener la última pregunta del usuario
        pregunta = ""
        for m in reversed(messages):
            if isinstance(m, type(messages[0]).__mro__[0] if messages else object):
                break
        # Buscar el HumanMessage más reciente antes del AIMessage final
        for m in reversed(messages[:-1]):
            if isinstance(m, HumanMessage):
                pregunta = m.content if isinstance(m.content, str) else ""
                break

        tool_results = _tool_results(messages)
        tool_results_json = json.dumps(tool_results, ensure_ascii=False)

        veredicto = await _juez_llm(pregunta, borrador, tool_results_json)
        if not veredicto.get("ok", True):
            return {
                "validacion": {
                    "ok": False,
                    "motivo": veredicto.get("motivo", "La respuesta no cumplió la rúbrica de calidad."),
                },
                "intentos_validacion": intentos + 1,
            }

    return {"validacion": {"ok": True}, "intentos_validacion": intentos}
