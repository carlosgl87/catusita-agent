from db.models import create_claim


async def registrar_reclamo(conversation_id: str, pedido_id: str, motivo: str) -> dict:
    numero = await create_claim(conversation_id, pedido_id, motivo)
    return {
        "numero_reclamo": numero,
        "estado": "registrado",
        "mensaje": f"Tu reclamo {numero} fue registrado. Un asesor te contactará en menos de 24 horas.",
        "pedido_id": pedido_id,
    }
