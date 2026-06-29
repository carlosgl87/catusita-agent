"""
Webhook que recibe los eventos `whatsapp.message.received` de Kapso
(WhatsApp Cloud API oficial).

El payload de Kapso (sandbox) llega en formato BATCH: los campos
relevantes (message, phone_number_id, conversation) vienen dentro de
`data: [ {...}, ... ]`, no en la raíz. Ejemplo real:

{
  "type": "whatsapp.message.received",
  "batch": true,
  "data": [
    {
      "message": {
        "from": "51940351180",
        "text":  { "body": "Hola" },
        "kapso": { "content": "Hola", "direction": "inbound" },
        "type": "text"
      },
      "conversation": { "phone_number_id": "597907523413541", ... },
      "is_new_conversation": true,
      "phone_number_id": "597907523413541"
    }
  ],
  "batch_info": { ... }
}

Headers:
  X-Webhook-Event:     whatsapp.message.received
  X-Webhook-Signature: <HMAC-SHA256 hex del body crudo con el secret>
  X-Idempotency-Key:   <uuid>
"""
import os
import uuid
import json
import asyncio
import logging

from fastapi import APIRouter, Request, HTTPException

from shared import auth
from shared import kapso as kapso_mod
from shared import waha as waha_mod
from shared import yahuar as yahuar_mod
from orchestrator import router as agent_router
from orchestrator.graph import run_agent_graph_full
from orchestrator import context
from db import models

router_wh = APIRouter()

# Referencias fuertes a las tareas en segundo plano para que el GC no las
# recoja a media ejecución (asyncio solo guarda weakrefs a las tasks).
_tareas_bg: set = set()

USE_AUTH_MOCK  = os.getenv("USE_AUTH_MOCK", "true").lower() == "true"
USE_LANGGRAPH  = os.getenv("USE_LANGGRAPH", "false").lower() == "true"
PERSIST_TO_DB  = os.getenv("PERSIST_TO_DB", "false").lower() == "true"
# WHATSAPP_PROVIDER=waha  →  usa WAHA para enviar mensajes
# WHATSAPP_PROVIDER=kapso →  usa Kapso (default)
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "kapso").lower()

KAPSO_PHONE_NUMBER_ID = os.getenv("KAPSO_PHONE_NUMBER_ID", "")

# Cuando agreguemos un número Kapso aparte para clientes, ponemos su
# phone_number_id acá y enrutamos. Por ahora solo tenemos el de vendedores.
KAPSO_PHONE_NUMBER_ID_CLIENTES = os.getenv("KAPSO_PHONE_NUMBER_ID_CLIENTES", "")


async def _abrir_conversacion(perfil: dict, agente_tipo: str, numero: str) -> str:
    """
    Crea un registro en la tabla conversations y devuelve su id.
    Si la BD falla genera un UUID local para no romper el flujo.
    En mock mode pasa user_id=None (la columna es nullable).
    """
    if PERSIST_TO_DB or not USE_AUTH_MOCK:
        try:
            user_id = None if USE_AUTH_MOCK else (perfil.get("user_id") or perfil.get("id"))
            return await models.create_conversation(user_id, agente_tipo, numero)
        except Exception as e:
            logging.error(f"Error guardando en DB: {e}", exc_info=True)
            print(f"Error guardando en DB (create_conversation): {e}")
    return str(uuid.uuid4())


def _resolver_agente_tipo(phone_number_id: str) -> str:
    """
    Decide si el mensaje va al agente de vendedores o de clientes
    según a qué phone_number_id de Kapso llegó.
    """
    if (
        KAPSO_PHONE_NUMBER_ID_CLIENTES
        and str(phone_number_id) == str(KAPSO_PHONE_NUMBER_ID_CLIENTES)
    ):
        return "cliente"
    # Por defecto: vendedores (es el primer número conectado).
    return "vendedor"


async def _procesar_item(item: dict) -> dict:
    """
    Procesa un único mensaje entrante de Kapso (un elemento del batch).
    """
    message = item.get("message") or {}
    # phone_number_id puede venir en la raíz del item o dentro de conversation
    phone_number_id = str(
        item.get("phone_number_id")
        or (item.get("conversation") or {}).get("phone_number_id")
        or ""
    )

    # ----------------------------------------------------------------------
    # Filtrar por phone_number_id esperado
    # ----------------------------------------------------------------------
    permitidos = {
        x for x in (KAPSO_PHONE_NUMBER_ID, KAPSO_PHONE_NUMBER_ID_CLIENTES) if x
    }
    if permitidos and phone_number_id not in {str(x) for x in permitidos}:
        print(
            f"[WEBHOOK] ignorado: phone_number_id={phone_number_id!r} "
            f"no está en {permitidos}"
        )
        return {"status": "ignored", "reason": "unknown phone_number_id"}

    # ----------------------------------------------------------------------
    # Extraer número del remitente y texto
    # ----------------------------------------------------------------------
    numero = (message.get("from") or "").lstrip("+").split("@")[0]

    # Texto: primero text.body; si no, kapso.content (incluye debouncing/agrupación)
    texto = (
        (message.get("text") or {}).get("body")
        or (message.get("kapso") or {}).get("content")
    )

    print(f"[WEBHOOK] numero={numero!r} texto={texto!r} phone_number_id={phone_number_id}")

    if not texto:
        print("[WEBHOOK] ignorado: mensaje sin texto (imagen/audio/sticker)")
        return {"status": "ignored", "reason": "no text"}

    if not numero:
        print("[WEBHOOK] ignorado: sin numero (message.from vacío)")
        return {"status": "ignored", "reason": "no from"}

    # ----------------------------------------------------------------------
    # Resolver agente tipo + autenticación
    # ----------------------------------------------------------------------
    agente_tipo = _resolver_agente_tipo(phone_number_id)
    print(f"[WEBHOOK] agente_tipo={agente_tipo}")

    perfil = await auth.get_user_profile(numero, agente_tipo)
    print(f"[WEBHOOK] perfil: {perfil}")

    if not perfil.get("autenticado"):
        print("[WEBHOOK] perfil no autenticado — pidiendo identificación")
        try:
            await kapso_mod.kapso.send_message(
                numero, phone_number_id, perfil.get("mensaje", "")
            )
        except Exception as e:
            logging.error(f"Error enviando msg de auth: {e}", exc_info=True)
            print(f"[WEBHOOK] ERROR enviando auth_required: {e}")
        return {"status": "auth_required"}

    # ----------------------------------------------------------------------
    # Comando de reset
    # ----------------------------------------------------------------------
    if texto.strip().lower() in ("reiniciar", "reset", "nueva conversacion"):
        print("[WEBHOOK] comando de reinicio")
        await context.clear_history(numero)
        await kapso_mod.kapso.send_message(
            numero, phone_number_id,
            "Conversación reiniciada. ¿En qué puedo ayudarte?",
        )
        return {"status": "ok"}

    # ----------------------------------------------------------------------
    # Ejecutar el agente
    # ----------------------------------------------------------------------
    conversation_id = await _abrir_conversacion(perfil, agente_tipo, numero)
    perfil["conversation_id"] = conversation_id
    # Datos de envío para que las tools puedan encolar media (ej. foto SUNARP)
    perfil["numero"] = numero
    perfil["phone_number_id"] = phone_number_id

    historial = await context.get_history(numero)
    print(
        f"[WEBHOOK] procesando con el router: "
        f"conversation_id={conversation_id} historial={len(historial)} msgs"
    )

    if USE_LANGGRAPH:
        respuesta, media_list = await run_agent_graph_full(texto, perfil, historial)
    else:
        respuesta = await agent_router.run_agent(texto, perfil, historial)
        media_list = perfil.get("_media_pendiente", [])

    print(f"[WEBHOOK] respuesta ({'LangGraph' if USE_LANGGRAPH else 'router'}): {respuesta!r}")

    # ----------------------------------------------------------------------
    # Persistir y enviar
    # ----------------------------------------------------------------------
    await context.save_message(numero, "user", texto)
    await context.save_message(numero, "assistant", respuesta)

    if PERSIST_TO_DB or not USE_AUTH_MOCK:
        try:
            await models.save_message(conversation_id, "user", texto)
            await models.save_message(conversation_id, "assistant", respuesta)
        except Exception as e:
            logging.error(f"Error guardando en DB: {e}", exc_info=True)
            print(f"Error guardando en DB (save_message): {e}")

    try:
        envio = await kapso_mod.kapso.send_message(numero, phone_number_id, respuesta)
        print(f"[WEBHOOK] enviado a WhatsApp -> {envio}")
    except Exception as e:
        logging.error(f"Error enviando mensaje por Kapso: {e}", exc_info=True)
        print(f"[WEBHOOK] ERROR enviando a WhatsApp: {e}")

    # ----------------------------------------------------------------------
    # Enviar media encolada por las tools (ej. foto de la tarjeta SUNARP)
    # ----------------------------------------------------------------------
    for media in media_list:
        try:
            await kapso_mod.kapso.send_image_base64(
                numero,
                phone_number_id,
                media["imagen_base64"],
                caption=media.get("caption", ""),
                filename=media.get("filename", "imagen.png"),
            )
            print(f"[WEBHOOK] foto enviada a WhatsApp ({media.get('filename')})")
        except Exception as e:
            logging.error(f"Error enviando imagen por Kapso: {e}", exc_info=True)
            print(f"[WEBHOOK] ERROR enviando imagen: {e}")

    return {"status": "ok"}


@router_wh.post("/whatsapp")
async def webhook_whatsapp(request: Request):
    # ----------------------------------------------------------------------
    # [0] Leer el body crudo para verificar la firma antes de parsearlo
    # ----------------------------------------------------------------------
    raw_body = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")
    event = request.headers.get("X-Webhook-Event", "")
    idempotency_key = request.headers.get("X-Idempotency-Key", "")

    print(
        f"[WEBHOOK] event={event!r} idempotency_key={idempotency_key!r} "
        f"sig={(signature[:16] + '...') if signature else 'MISSING'}"
    )

    if not kapso_mod.verify_signature(raw_body, signature):
        print("[WEBHOOK] firma inválida — rechazado")
        raise HTTPException(status_code=401, detail="invalid signature")

    # ----------------------------------------------------------------------
    # [1] Parsear el JSON ya verificado
    # ----------------------------------------------------------------------
    try:
        data = json.loads(raw_body)
    except Exception as e:
        print(f"[WEBHOOK] body no es JSON válido: {e}")
        raise HTTPException(status_code=400, detail="invalid json")

    try:
        print(f"[WEBHOOK] body recibido: {json.dumps(data, ensure_ascii=False)}")
    except Exception:
        print(f"[WEBHOOK] body recibido (raw): {data}")

    # ----------------------------------------------------------------------
    # [2] Sólo nos interesan los `whatsapp.message.received`.
    #     El tipo viene en el header X-Webhook-Event y/o en data["type"].
    #     Otros eventos (sent / delivered / read / failed / conversation.*)
    #     los reconocemos con 200 OK y los ignoramos.
    # ----------------------------------------------------------------------
    tipo_evento = event or data.get("type", "")
    if tipo_evento != "whatsapp.message.received":
        print(f"[WEBHOOK] ignorado: evento {tipo_evento!r} no relevante")
        return {"status": "ignored", "reason": f"event {tipo_evento}"}

    # ----------------------------------------------------------------------
    # [2.5] IDEMPOTENCIA: si Kapso reenvía el mismo webhook (porque tardamos
    #       en responderle el 200), NO lo reprocesamos. Sin esto, una consulta
    #       lenta (ej. SUNARP caído) hace que Kapso reintente y cada reintento
    #       dispare otra ejecución del agente → decenas de respuestas repetidas.
    # ----------------------------------------------------------------------
    if idempotency_key and await context.ya_procesado(idempotency_key):
        print(f"[WEBHOOK] idempotente: {idempotency_key!r} ya procesado, ignorando")
        return {"status": "ignored", "reason": "duplicate idempotency_key"}

    # ----------------------------------------------------------------------
    # [3] El payload puede venir en batch (data: [ {...}, ... ]) o como un
    #     único objeto en la raíz. Normalizamos a una lista.
    # ----------------------------------------------------------------------
    items = data.get("data")
    if not isinstance(items, list):
        items = [data]

    # ----------------------------------------------------------------------
    # [4] ACK INMEDIATO + procesamiento en segundo plano.
    #
    #     Kapso espera el 200 OK en pocos segundos; si tardamos (porque el
    #     agente llama una tool lenta, ej. SUNARP), Kapso da por fallida la
    #     entrega y REENVÍA el webhook → cada reenvío genera otra respuesta
    #     al usuario (el spam que veíamos). La solución correcta es responder
    #     200 al instante y hacer el trabajo del agente aparte, de modo que
    #     Kapso nunca tenga motivo para reintentar.
    # ----------------------------------------------------------------------
    tarea = asyncio.create_task(_procesar_items_bg(items))
    _tareas_bg.add(tarea)
    tarea.add_done_callback(_tareas_bg.discard)

    return {"status": "accepted"}


async def _procesar_items_bg(items: list) -> None:
    """Procesa los mensajes del batch fuera del ciclo request/response.

    Se ejecuta después de haberle devuelto el 200 a Kapso, así una tool lenta
    nunca provoca reintentos del webhook. Cada item se aísla en su try/except
    para que un error en uno no tumbe a los demás.
    """
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            await _procesar_item(item)
        except Exception as e:
            logging.error(f"Error procesando item del webhook: {e}", exc_info=True)
            print(f"[WEBHOOK] ERROR procesando item (bg): {e}")


# ---------------------------------------------------------------------------
# Selector de proveedor de mensajería
# ---------------------------------------------------------------------------

def _messenger():
    """Devuelve el cliente activo según WHATSAPP_PROVIDER."""
    if WHATSAPP_PROVIDER == "waha":
        return waha_mod.waha
    return kapso_mod.kapso


# ---------------------------------------------------------------------------
# Webhook de WAHA
# ---------------------------------------------------------------------------

async def _procesar_item_waha(data: dict) -> dict:
    """
    Normaliza el payload de WAHA y lo procesa con la misma lógica interna.

    Formato WAHA (versión 2026.x):
    {
      "event": "message",
      "session": "default",
      "payload": {
        "id": "...",
        "from": "51940351180@c.us",
        "fromMe": false,
        "body": "Hola",
        "type": "chat"
      }
    }
    """
    event   = data.get("event", "")
    payload = data.get("payload") or {}

    # Solo mensajes entrantes de texto
    if event != "message":
        print(f"[WAHA] ignorado: evento {event!r}")
        return {"status": "ignored", "reason": f"event {event}"}

    if payload.get("fromMe"):
        print("[WAHA] ignorado: fromMe=true")
        return {"status": "ignored", "reason": "fromMe"}

    tipo = payload.get("type", "")
    if tipo not in ("chat", "text", ""):
        print(f"[WAHA] ignorado: tipo {tipo!r} (no es texto)")
        return {"status": "ignored", "reason": f"type {tipo}"}

    from_field = payload.get("from") or ""          # ej. "51940351180@c.us" o "111@lid"
    numero     = from_field.split("@")[0].lstrip("+")   # para auth y Redis
    texto      = payload.get("body") or ""

    print(f"[WAHA] from={from_field!r} numero={numero!r} texto={texto!r}", flush=True)

    if not from_field:
        print("[WAHA] ignorado: no from", flush=True)
        return {"status": "ignored", "reason": "no from"}

    # ── Respuesta de Yahuar ──────────────────────────────────────────────────
    # Yahuar puede tener un LID diferente a su número de teléfono, así que
    # en vez de comparar por número comparamos por contexto: si hay una consulta
    # pendiente en Redis Y el mensaje NO viene del usuario que hizo la consulta,
    # es la respuesta de Yahuar.
    pendiente_peek = await yahuar_mod.peek_pendiente()
    if pendiente_peek and from_field != pendiente_peek.get("from_field"):
        print(f"[WAHA] respuesta de Yahuar detectada por Redis (sender={from_field!r})", flush=True)
        return await _manejar_respuesta_yahuar(payload)

    if not texto:
        print("[WAHA] ignorado: no texto", flush=True)
        return {"status": "ignored", "reason": "no text"}

    # Reutilizamos toda la lógica del agente — phone_number_id vacío porque
    # WAHA no tiene ese concepto (usamos session en su lugar).
    agente_tipo = "vendedor"  # por ahora solo el canal de vendedores
    perfil = await auth.get_user_profile(numero, agente_tipo)
    print(f"[WAHA] perfil: {perfil}", flush=True)

    if not perfil.get("autenticado"):
        await _messenger().send_message(from_field, "", perfil.get("mensaje", ""))
        return {"status": "auth_required"}

    if texto.strip().lower() in ("reiniciar", "reset", "nueva conversacion"):
        await context.clear_history(numero)
        await _messenger().send_message(from_field, "", "Conversación reiniciada. ¿En qué puedo ayudarte?")
        return {"status": "ok"}

    conversation_id = await _abrir_conversacion(perfil, agente_tipo, numero)
    perfil["conversation_id"] = conversation_id
    perfil["numero"]          = numero
    perfil["from_field"]      = from_field   # necesario para Yahuar relay
    perfil["phone_number_id"] = ""

    historial = await context.get_history(numero)

    if USE_LANGGRAPH:
        respuesta, media_list = await run_agent_graph_full(texto, perfil, historial)
    else:
        respuesta = await agent_router.run_agent(texto, perfil, historial)
        media_list = perfil.get("_media_pendiente", [])

    await context.save_message(numero, "user", texto)
    await context.save_message(numero, "assistant", respuesta)

    if PERSIST_TO_DB or not USE_AUTH_MOCK:
        try:
            await models.save_message(conversation_id, "user", texto)
            await models.save_message(conversation_id, "assistant", respuesta)
        except Exception as e:
            logging.error(f"Error guardando en DB (WAHA): {e}", exc_info=True)

    try:
        await _messenger().send_message(from_field, "", respuesta)
        print(f"[WAHA] respuesta enviada a {from_field!r}")
    except Exception as e:
        logging.error(f"Error enviando por WAHA: {e}", exc_info=True)
        print(f"[WAHA] ERROR enviando: {e}")

    for media in media_list:
        try:
            await _messenger().send_image_base64(
                from_field, "",
                media["imagen_base64"],
                caption=media.get("caption", ""),
                filename=media.get("filename", "imagen.png"),
            )
        except Exception as e:
            print(f"[WAHA] ERROR enviando imagen: {e}")

    return {"status": "ok"}


async def _manejar_respuesta_yahuar(payload: dict) -> dict:
    """
    Yahuar respondió con la info de la placa.
    Busca en Redis a quién estaba esperando y le reenvía texto + foto.
    """
    pendiente = await yahuar_mod.get_pendiente()
    if not pendiente:
        print("[YAHUAR] respuesta recibida pero no hay consulta pendiente en Redis")
        return {"status": "ignored", "reason": "no pending"}

    destino    = pendiente["from_field"]
    placa      = pendiente.get("placa", "")
    texto_resp = payload.get("body") or ""
    has_media  = payload.get("hasMedia", False)
    media      = payload.get("media") or {}

    print(f"[YAHUAR] respuesta para {destino!r} placa={placa!r} hasMedia={has_media}")

    messenger = _messenger()

    # Enviar texto si lo hay
    if texto_resp:
        try:
            await messenger.send_message(destino, "", texto_resp)
        except Exception as e:
            print(f"[YAHUAR] ERROR enviando texto: {e}")

    # Enviar imagen si la hay (viene en base64 con WHATSAPP_HOOK_MEDIA_INLINE=true)
    if has_media and media.get("data"):
        try:
            await messenger.send_image_base64(
                destino, "",
                media["data"],
                caption=f"Placa {placa}",
                filename=f"placa_{placa}.jpg",
            )
        except Exception as e:
            print(f"[YAHUAR] ERROR enviando imagen: {e}")

    return {"status": "ok"}


@router_wh.post("/waha")
async def webhook_waha(request: Request):
    """Recibe eventos de WAHA (message, message.ack, session.status, etc.)."""
    raw_body = await request.body()

    # Verificación simple por API key en header (opcional pero recomendado)
    waha_key = request.headers.get("X-Api-Key", "")
    expected = os.getenv("WAHA_WEBHOOK_TOKEN", "")
    if expected and waha_key != expected:
        print(f"[WAHA] token inválido: {waha_key!r}")
        raise HTTPException(status_code=401, detail="invalid token")

    try:
        data = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    event_name = data.get("event", "")
    payload_preview = str(data)[:300]
    print(f"[WAHA] evento recibido: {event_name!r} payload={payload_preview}", flush=True)

    tarea = asyncio.create_task(_procesar_item_waha_bg(data))
    _tareas_bg.add(tarea)
    tarea.add_done_callback(_tareas_bg.discard)

    return {"status": "accepted"}


async def _procesar_item_waha_bg(data: dict) -> None:
    try:
        print("[WAHA] bg: iniciando procesamiento", flush=True)
        await _procesar_item_waha(data)
        print("[WAHA] bg: procesamiento completado", flush=True)
    except Exception as e:
        logging.error(f"Error procesando evento WAHA: {e}", exc_info=True)
        print(f"[WAHA] ERROR en background: {e}", flush=True)
