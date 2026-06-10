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
import logging

from fastapi import APIRouter, Request, HTTPException

from shared import auth
from shared import kapso as kapso_mod
from orchestrator import router as agent_router
from orchestrator.graph import run_agent_graph_full
from orchestrator import context
from db import models

router_wh = APIRouter()

USE_AUTH_MOCK = os.getenv("USE_AUTH_MOCK", "true").lower() == "true"
USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "false").lower() == "true"
KAPSO_PHONE_NUMBER_ID = os.getenv("KAPSO_PHONE_NUMBER_ID", "")

# Cuando agreguemos un número Kapso aparte para clientes, ponemos su
# phone_number_id acá y enrutamos. Por ahora solo tenemos el de vendedores.
KAPSO_PHONE_NUMBER_ID_CLIENTES = os.getenv("KAPSO_PHONE_NUMBER_ID_CLIENTES", "")


async def _abrir_conversacion(perfil: dict, agente_tipo: str, numero: str) -> str:
    """
    Crea un registro en la tabla conversations y devuelve su id.
    En modo mock (o si la BD falla) genera un UUID local para no romper el flujo.
    """
    if not USE_AUTH_MOCK:
        try:
            user_id = perfil.get("user_id") or perfil.get("id")
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
    # [3] El payload puede venir en batch (data: [ {...}, ... ]) o como un
    #     único objeto en la raíz. Normalizamos a una lista y procesamos cada
    #     mensaje por separado.
    # ----------------------------------------------------------------------
    items = data.get("data")
    if not isinstance(items, list):
        items = [data]

    resultados = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            resultados.append(await _procesar_item(item))
        except Exception as e:
            logging.error(f"Error procesando item del webhook: {e}", exc_info=True)
            print(f"[WEBHOOK] ERROR procesando item: {e}")
            resultados.append({"status": "error"})

    return {"status": "ok", "items": resultados}
