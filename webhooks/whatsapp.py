import os
from fastapi import APIRouter, Request
from shared import auth, evolution
from orchestrator import router as agent_router
from orchestrator import context

router_wh = APIRouter()

INSTANCE_VENDEDORES = os.getenv("EVOLUTION_INSTANCE_VENDEDORES", "catusita-vendedores")
INSTANCE_CLIENTES = os.getenv("EVOLUTION_INSTANCE_CLIENTES", "catusita-clientes")


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

    historial = await context.get_history(numero)
    respuesta = await agent_router.run_agent(texto, perfil, historial)

    await context.save_message(numero, "user", texto)
    await context.save_message(numero, "assistant", respuesta)
    await evolution.evolution.send_message(numero, instance_name, respuesta)

    return {"status": "ok"}
