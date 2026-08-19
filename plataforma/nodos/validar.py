"""Guardián de la salida. Revisa la respuesta antes de que llegue a WhatsApp.

Si falla, devuelve el control al orquestador con el motivo, hasta MAX_REINTENTOS.
Es la razón por la que ningún área puede ir a END: toda respuesta pasa por acá.

── El mecanismo es común, las reglas NO ───────────────────────────────────────

Lo que para un vendedor es normal —precio neto, cartera, descuento— para un
cliente es una fuga. Por eso las reglas se eligen por multiagente (`_REGLAS`) y
el nodo se construye con una fábrica, igual que `contexto`.

── Capas, de barata a cara ────────────────────────────────────────────────────

  1. PRIVACIDAD          regex. Bloquea que se revele un dato restringido.
  2. REPREGUNTA          ya teníamos el dato resuelto y el agente igual lo pidió.
  3. NO USÓ TOOLS        contestó pidiendo datos teniendo con qué consultarlos.
  4. JUEZ LLM            solo si se tocaron tools sensibles. Es la única que cuesta.

El orden importa: las tres primeras no gastan tokens, así que la cuarta corre
sobre lo que ya pasó el filtro barato.

── Reintentos ─────────────────────────────────────────────────────────────────

MAX_REINTENTOS = 1. Si el agente ya corrigió una vez y la segunda validación
también falla, se deja pasar con WARNING: un loop infinito de correcciones deja
al usuario sin respuesta, que es peor que una respuesta imperfecta.

Migrado desde orchestrator/nodes/validar.py.
"""
import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from plataforma import llm
from plataforma.estado import EstadoAgente

MAX_REINTENTOS = 1

# Tools cuyo resultado justifica pagar el juez LLM.
_TOOLS_SENSIBLES = {"consultar_perfil_cliente"}


# ─── Reglas de privacidad, por multiagente ───────────────────────────────────
#
# Solo bloquear cuando el agente REVELA el dato (con número o lugar), NO cuando
# lo menciona para decir que no puede compartirlo. Por eso casi todos los
# patrones exigen un número al lado.

_PROHIBIDO_VENDEDORES = [
    # Lo que un asesor no debe reenviarle a un cliente.
    r"precio\s*neto[^.\n]{0,30}\d[\d.,]*",
    r"sin\s*igv[^.\n]{0,30}s?/?\s*\.?\s*\d[\d.,]*",
    r"descuento[^.\n]{0,20}(del?\s*\d+\s*%|\d+[\d.,]*\s*sol)",
    r"alm[aá]cen\s+(de\s+)?(miraflores|ate|lima|callao|san\s*isidro)",
    r"hora\s*de\s*reparto[^.\n]{0,20}\d{1,2}[:\s*h]",
    r"ruta\s+(de\s+)?reparto",
]

# Para clientes es MÁS estricto, no menos: acá ni siquiera existe el permiso.
# Un cliente nunca ve neto, cartera ni condición de crédito, con número o sin él.
_PROHIBIDO_CLIENTES = _PROHIBIDO_VENDEDORES + [
    r"precio\s*neto",
    r"l[ií]mite\s+de\s+cr[eé]dito",
    r"deuda\s+(actual|pendiente)",
    r"cartera\s+(del?\s+)?(asesor|vendedor)",
    r"letra[s]?\s+(por\s+)?vencer",
]

_REGLAS = {
    "vendedores":   _PROHIBIDO_VENDEDORES,
    "clientes":     _PROHIBIDO_CLIENTES,
    # Los supervisores ven lo de vendedores. Se revisa cuando se defina su alcance.
    "supervisores": _PROHIBIDO_VENDEDORES,
}

_COMPILADAS = {
    k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in _REGLAS.items()
}


# ─── Patrones de repregunta ──────────────────────────────────────────────────

_RE_PIDE_RUC = re.compile(
    r"(¿.{0,50}(proporcionar?|indicar?|dar?|confirmar?)\s+(el\s+)?ruc)"
    r"|(necesito\s+(el\s+)?ruc)"
    r"|(por\s+favor.{0,20}ruc)"
    r"|(¿cu[aá]l\s+es\s+(el\s+)?ruc\s*(del\s+cliente)?\?)",
    re.IGNORECASE,
)
_RE_PIDE_PEDIDO = re.compile(
    r"(¿.{0,50}(proporcionar?|indicar?|dar?|confirmar?)\s+(el\s+)?(n[uú]mero\s+de\s+pedido|id\s+del\s+pedido))"
    r"|(necesito\s+(el\s+)?(n[uú]mero\s+de\s+pedido|id\s+del\s+pedido))",
    re.IGNORECASE,
)
_RE_REPREGUNTA = re.compile(
    r"(¿.{0,40}(proporcionar?|indicar?|dar?|facilitar?|confirmar?)\s+(el\s+)?"
    r"(ruc|n[uú]mero\s+de\s+pedido|c[oó]digo\s+(sku|del\s+producto)|n[uú]mero\s+de\s+cliente))"
    r"|(necesito\s+(el\s+)?(ruc|n[uú]mero\s+de\s+pedido|c[oó]digo\s+sku))"
    r"|(por\s+favor.{0,20}(ruc|n[uú]mero\s+de\s+pedido|c[oó]digo\s+sku))",
    re.IGNORECASE,
)
_RE_REQUIERE_DATOS = re.compile(
    r"\b(stock|precio|pedido|cr[eé]dito|factura|gu[ií]a|cobranza|letra|saldo|"
    r"disponible|inventario|estado del|ruc|placa)\b",
    re.IGNORECASE,
)

_RUBRICA = """Eres un auditor de respuestas del agente comercial de Catusita.
Revisa SOLO estos dos tipos de violaciones serias. Ignora todo lo demás.

VIOLACIÓN A — PRIVACIDAD CRÍTICA:
  El agente reveló un VALOR NUMÉRICO concreto de precio neto o descuento porcentual
  de negociación que no debería compartir. Ej: "el precio neto es S/ 45.00".
  NO cuenta como violación: mencionar "precio neto" para decir que no puede darlo.

VIOLACIÓN B — AUTORIZACIÓN FALSA:
  El agente afirmó que él mismo aprobó o autorizará una excepción de crédito, un
  precio especial o un cambio de condiciones (cosas que requieren al supervisor).

Si no hay ninguna de estas dos violaciones -> responde {{"ok": true}}.
Si hay alguna -> {{"ok": false, "motivo": "..."}} (1 oración en español, concisa).

Pregunta: {pregunta}
Respuesta del agente: {borrador}
"""


# ─── Lectura del estado ──────────────────────────────────────────────────────

def _borrador(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


def _ultima_pregunta(messages: list) -> str:
    for m in reversed(messages[:-1]):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else ""
    return ""


def _tools_usadas(messages: list) -> set[str]:
    usadas = set()
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                usadas.add(tc.get("name", ""))
    return usadas


def _hubo_tools(messages: list) -> bool:
    return any(isinstance(m, ToolMessage) for m in messages)


# ─── Reglas ──────────────────────────────────────────────────────────────────

def _r1_privacidad(borrador: str, multiagente: str) -> str | None:
    for r in _COMPILADAS.get(multiagente, []):
        if r.search(borrador):
            return (
                "La respuesta revela información restringida (precio neto, descuento, "
                "ubicación de almacén, ruta de reparto o datos de crédito). Omite ese "
                "dato y responde solo con lo que sí se puede compartir."
            )
    return None


def _r2_repregunta(borrador: str, resuelto: dict) -> str | None:
    """No sirve mientras `resuelto` esté vacío — que es hoy, hasta que se migre
    el extractor de entidades a `contexto`. Se deja porque el día que exista
    empieza a funcionar sin tocar nada."""
    if not resuelto:
        return None
    if resuelto.get("ruc") and _RE_PIDE_RUC.search(borrador):
        return (f"Ya tienes el RUC del cliente ({resuelto['ruc']}). "
                f"Úsalo directamente en las tools, no se lo pidas al usuario.")
    if resuelto.get("pedido") and _RE_PIDE_PEDIDO.search(borrador):
        return (f"Ya tienes el ID del pedido ({resuelto['pedido']}). "
                f"Úsalo directamente en las tools.")
    return None


def _r3_no_uso_tools(borrador: str, pregunta: str, hubo: bool, resuelto: dict) -> str | None:
    if hubo or not _RE_REQUIERE_DATOS.search(pregunta):
        return None
    # Con pedido pero sin RUC, pedir el RUC es legítimo: es un límite del API,
    # no un descuido del agente.
    if resuelto.get("pedido") and not resuelto.get("ruc"):
        return None
    if _RE_REPREGUNTA.search(borrador):
        return ("Tenías tools disponibles para responder esto. En lugar de pedirle "
                "datos al usuario, úsalas con la información que ya tienes.")
    return None


async def _r4_juez(pregunta: str, borrador: str) -> dict:
    try:
        r = await llm.crear_mensaje(
            system="Auditor de respuestas. Responde SOLO con JSON válido, sin texto adicional.",
            messages=[{"role": "user", "content": _RUBRICA.format(
                pregunta=pregunta, borrador=borrador)}],
            max_tokens=150,
        )
        crudo = "".join(b.text for b in r.content if hasattr(b, "text")).strip()
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        logging.error(f"validar: el juez falló ({e})")
    # Fallback permisivo A PROPÓSITO: si el auditor se cae, no se bloquea la
    # conversación. Las tres reglas baratas ya corrieron y son las que atajan lo
    # grave; el juez es una segunda pasada, no la única defensa.
    return {"ok": True}


# ─── Nodo ────────────────────────────────────────────────────────────────────

def hacer_nodo_validar(multiagente: str):
    """Devuelve el nodo `validar` de UN multiagente, con sus reglas."""

    async def nodo_validar(state: EstadoAgente) -> dict:
        messages = list(state.get("messages", []))
        resuelto = state.get("resuelto") or {}
        intentos = state.get("intentos_validacion", 0)

        borrador = _borrador(messages)
        if not borrador:
            return {"validacion": {"ok": True}}

        if intentos >= MAX_REINTENTOS:
            logging.warning("validar: tope de reintentos, se deja pasar.")
            return {"validacion": {"ok": True}, "intentos_validacion": intentos}

        pregunta = _ultima_pregunta(messages)

        def rechazar(motivo: str) -> dict:
            logging.warning(f"validar RECHAZÓ ({multiagente}, intento {intentos}): {motivo[:100]}")
            return {"validacion": {"ok": False, "motivo": motivo},
                    "intentos_validacion": intentos + 1}

        for motivo in (
            _r1_privacidad(borrador, multiagente),
            _r2_repregunta(borrador, resuelto),
            _r3_no_uso_tools(borrador, pregunta, _hubo_tools(messages), resuelto),
        ):
            if motivo:
                return rechazar(motivo)

        if _tools_usadas(messages) & _TOOLS_SENSIBLES:
            veredicto = await _r4_juez(pregunta, borrador)
            if not veredicto.get("ok", True):
                return rechazar(veredicto.get("motivo",
                                              "La respuesta no superó la auditoría."))

        return {"validacion": {"ok": True}, "intentos_validacion": intentos}

    return nodo_validar
