import os
import uuid
import json
import logging
from fastapi import APIRouter, Request
from shared import auth, evolution
from orchestrator import router as agent_router
from orchestrator import context
from db import models

router_wh = APIRouter()

INSTANCE_VENDEDORES = os.getenv("EVOLUTION_INSTANCE_VENDEDORES", "catusita-vendedores")
INSTANCE_CLIENTES = os.getenv("EVOLUTION_INSTANCE_CLIENTES", "catusita-clientes")
USE_AUTH_MOCK = os.getenv("USE_AUTH_MOCK", "true").lower() == "true"


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


@router_wh.post("/whatsapp")
async def webhook_whatsapp(request: Request):
    data = await request.json()

    # [1] Body completo entrante
    try:
        print(f"[WEBHOOK] body recibido: {json.dumps(data, ensure_ascii=False)}")
    except Exception:
        print(f"[WEBHOOK] body recibido (raw): {data}")

    # Ignorar mensajes enviados por nosotros
    if data.get("data", {}).get("key", {}).get("fromMe"):
        print("[WEBHOOK] descartado: mensaje propio (fromMe=true)")
        return {"status": "ignored"}

    msg_data = data.get("data", {})
    message = msg_data.get("message", {})

    texto = (
        message.get("conversation")
        or message.get("extendedTextMessage", {}).get("text")
    )
    numero = msg_data.get("key", {}).get("remoteJid", "").replace("@s.whatsapp.net", "")

    # [2] Número y texto extraídos
    print(f"[WEBHOOK] numero={numero!r} texto={texto!r}")

    if not texto:
        print("[WEBHOOK] descartado: sin texto (no es mensaje de texto)")
        return {"status": "ignored"}

    if not numero:
        print("[WEBHOOK] descartado: sin numero (remoteJid vacío)")
        return {"status": "ignored"}

    instance_name = data.get("instance", "")
    agente_tipo = "vendedor" if INSTANCE_VENDEDORES in instance_name else "cliente"
    print(f"[WEBHOOK] instance={instance_name!r} agente_tipo={agente_tipo}")

    perfil = await auth.get_user_profile(numero, agente_tipo)
    # [3] Resultado de la búsqueda de perfil
    print(f"[WEBHOOK] perfil: {perfil}")

    if not perfil.get("autenticado"):
        print("[WEBHOOK] descartado: perfil no autenticado -> se pide identificación")
        await evolution.evolution.send_message(numero, instance_name, perfil.get("mensaje", ""))
        return {"status": "auth_required"}

    if texto.strip().lower() in ("reiniciar", "reset", "nueva conversacion"):
        print("[WEBHOOK] comando de reinicio de conversación")
        await context.clear_history(numero)
        await evolution.evolution.send_message(numero, instance_name, "Conversación reiniciada. ¿En qué puedo ayudarte?")
        return {"status": "ok"}

    # Abrir conversación en BD y propagar el id real al router
    conversation_id = await _abrir_conversacion(perfil, agente_tipo, numero)
    perfil["conversation_id"] = conversation_id

    historial = await context.get_history(numero)
    # [4] A punto de procesar con el agente
    print(f"[WEBHOOK] procesando con el router: conversation_id={conversation_id} historial={len(historial)} msgs")

    respuesta = await agent_router.run_agent(texto, perfil, historial)
    print(f"[WEBHOOK] respuesta del router: {respuesta!r}")

    # Historial en Redis (corto plazo)
    await context.save_message(numero, "user", texto)
    await context.save_message(numero, "assistant", respuesta)

    # Persistencia en Postgres (best-effort: no debe romper el flujo)
    try:
        await models.save_message(conversation_id, "user", texto)
        await models.save_message(conversation_id, "assistant", respuesta)
    except Exception as e:
        logging.error(f"Error guardando en DB: {e}", exc_info=True)
        print(f"Error guardando en DB (save_message): {e}")

    try:
        envio = await evolution.evolution.send_message(numero, instance_name, respuesta)
        print(f"[WEBHOOK] enviado a WhatsApp -> {envio}")
    except Exception as e:
        logging.error(f"Error enviando mensaje por Evolution: {e}", exc_info=True)
        print(f"[WEBHOOK] ERROR enviando a WhatsApp: {e}")

    return {"status": "ok"}
