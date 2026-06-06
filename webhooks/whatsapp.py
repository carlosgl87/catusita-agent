"""
Webhook que recibe los eventos `whatsapp.message.received` de Kapso
(WhatsApp Cloud API oficial).

Payload típico (campos relevantes según docs.kapso.ai):

{
  "phone_number_id": "597907523413541",
  "is_new_conversation": false,
  "conversation": { "phone_number": "+15551234567" },
  "message": {
    "from": "51940351180",
    "from_user_id": "...",
    "username": "...",
    "text":  { "body": "hola" },
    "kapso": { "content": "hola", "direction": "inbound" },
    "timestamp": 1717891234
  }
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
from orchestrator import context
from db import models

router_wh = APIRouter()

USE_AUTH_MOCK = os.getenv("USE_AUTH_MOCK", "true").lower() == "true"
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


@router_wh.post("/whatsapp")
async def webhook_whatsapp(request: Request):
    # ----------------------------------------------------------------------
    # [0] Leer el body crudo + loguear headers para diagnosticar
    # ----------------------------------------------------------------------
    raw_body = await request.body()

    # Log de TODAS las headers para entender qué manda Kapso realmente
    all_headers = {k: v for k, v in request.headers.items()}
    print(f"[WEBHOOK] headers: {all_headers}")

    # Probar varios nombres posibles (Kapso, Meta-style, genérico)
    signature = (
        request.headers.get("X-Webhook-Signature")
        or request.headers.get("X-Hub-Signature-256")
        or request.headers.get("X-Kapso-Signature")
        or request.headers.get("X-Signature")
        or ""
    )
    event = (
        request.headers.get("X-Webhook-Event")
        or request.headers.get("X-Kapso-Event")
        or ""
    )
    idempotency_key = request.headers.get("X-Idempotency-Key", "")

    print(
        f"[WEBHOOK] event={event!r} idempotency_key={idempotency_key!r} "
        f"sig={(signature[:16] + '...') if signature else 'MISSING'}"
    )

    # Por ahora: validamos la firma SI viene; si no viene, dejamos pasar
    # con WARNING (modo permisivo) hasta entender el formato exacto de Kapso.
    # TODO: volver a hacerlo obligatorio una vez confirmado el header.
    if signature and not kapso_mod.verify_signature(raw_body, signature):
        print("[WEBHOOK] firma inválida — rechazado")
        raise HTTPException(status_code=401, detail="invalid signature")
    if not signature:
        print("[WEBHOOK] AVISO: request sin firma, aceptado en modo permisivo")

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
    #     Otros eventos (sent / delivered / read / failed / conversation.*)
    #     los reconocemos con 200 OK y los ignoramos.
    #     Si event viene vacío, intentamos inferir por el body (modo
    #     permisivo mientras confirmamos el formato real de Kapso).
    # ----------------------------------------------------------------------
    if event and event != "whatsapp.message.received":
        # Si vino un evento distinto al esperado, lo ignoramos.
        # Pero si vino vacío, seguimos y dejamos que el parseo del body decida.
        if "message" not in event and event not in ("", "received"):
            print(f"[WEBHOOK] ignorado: evento {event!r} no relevante")
            return {"status": "ignored", "reason": f"event {event}"}

    message = data.get("message") or {}
    phone_number_id = str(data.get("phone_number_id") or "")

    # ----------------------------------------------------------------------
    # [3] Filtrar por phone_number_id esperado
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
    # [4] Extraer número del remitente y texto
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
    # [5] Resolver agente tipo + autenticación
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
    # [6] Comando de reset
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
    # [7] Ejecutar el agente
    # ----------------------------------------------------------------------
    conversation_id = await _abrir_conversacion(perfil, agente_tipo, numero)
    perfil["conversation_id"] = conversation_id

    historial = await context.get_history(numero)
    print(
        f"[WEBHOOK] procesando con el router: "
        f"conversation_id={conversation_id} historial={len(historial)} msgs"
    )

    respuesta = await agent_router.run_agent(texto, perfil, historial)
    print(f"[WEBHOOK] respuesta del router: {respuesta!r}")

    # ----------------------------------------------------------------------
    # [8] Persistir y enviar
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

    return {"status": "ok"}
