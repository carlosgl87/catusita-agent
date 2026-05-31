import os
import uuid
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
            return await models.create_conversation(perfil["user_id"], agente_tipo, numero)
        except Exception:
            pass
    return str(uuid.uuid4())


@router_wh.post("/whatsapp")
async def webhook_whatsapp(request: Request):
    data = await request.json()

    # Ignorar mensajes enviados por nosotros
    if data.get("data", {}).get("key", {}).get("fromMe"):
        return {"status": "ignored"}

    msg_data = data.get("data", {})
    message = msg_data.get("message", {})

    texto = (
        message.get("conversation")
        or message.get("extendedTextMessage", {}).get("text")
    )
    if not texto:
        return {"status": "ignored"}

    numero = msg_data.get("key", {}).get("remoteJid", "").replace("@s.whatsapp.net", "")
    if not numero:
        return {"status": "ignored"}

    instance_name = data.get("instance", "")
    agente_tipo = "vendedor" if INSTANCE_VENDEDORES in instance_name else "cliente"

    perfil = await auth.get_user_profile(numero, agente_tipo)
    if not perfil.get("autenticado"):
        await evolution.evolution.send_message(numero, instance_name, perfil.get("mensaje", ""))
        return {"status": "auth_required"}

    if texto.strip().lower() in ("reiniciar", "reset", "nueva conversacion"):
        await context.clear_history(numero)
        await evolution.evolution.send_message(numero, instance_name, "Conversación reiniciada. ¿En qué puedo ayudarte?")
        return {"status": "ok"}

    # Abrir conversación en BD y propagar el id real al router
    conversation_id = await _abrir_conversacion(perfil, agente_tipo, numero)
    perfil["conversation_id"] = conversation_id

    historial = await context.get_history(numero)
    respuesta = await agent_router.run_agent(texto, perfil, historial)

    # Historial en Redis (corto plazo)
    await context.save_message(numero, "user", texto)
    await context.save_message(numero, "assistant", respuesta)

    # Persistencia en Postgres (best-effort: no debe romper el flujo)
    try:
        await models.save_message(conversation_id, "user", texto)
        await models.save_message(conversation_id, "assistant", respuesta)
    except Exception:
        pass

    await evolution.evolution.send_message(numero, instance_name, respuesta)

    return {"status": "ok"}
