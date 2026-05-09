import os
from db import models

USE_MOCK = os.getenv("USE_SAP_MOCK", "true").lower() == "true"

# Usuarios mock para desarrollo sin base de datos
_MOCK_ASESORES = {
    "51987654321": {
        "user_id": "asesor-001",
        "tipo": "asesor",
        "nombre": "Luis García",
        "linea_asignada": "filtros y lubricantes",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-001",
        "autenticado": True,
    },
    "51912345678": {
        "user_id": "asesor-002",
        "tipo": "asesor",
        "nombre": "María Torres",
        "linea_asignada": "frenos y suspensión",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-002",
        "autenticado": True,
    },
}

_MOCK_CLIENTES_RUC = {
    "20512345678": {
        "user_id": "cliente-001",
        "tipo": "cliente",
        "nombre": "Taller San Juan SRL",
        "ruc": "20512345678",
        "nivel_acceso": "basico",
        "autenticado": True,
    },
    "20601234567": {
        "user_id": "cliente-002",
        "tipo": "cliente",
        "nombre": "Auto Repuestos Lima SAC",
        "ruc": "20601234567",
        "nivel_acceso": "basico",
        "autenticado": True,
    },
}


async def get_user_profile(numero_whatsapp: str, agente_tipo: str) -> dict:
    if USE_MOCK:
        if agente_tipo == "vendedor":
            perfil = _MOCK_ASESORES.get(numero_whatsapp)
            if perfil:
                return perfil
            return {"autenticado": False, "tipo": "asesor",
                    "mensaje": "Tu número no está registrado. Contacta a tu supervisor."}
        else:
            # Para clientes en mock, aceptar cualquier número con estado no-autenticado
            return {
                "autenticado": False,
                "tipo": "cliente",
                "numero_whatsapp": numero_whatsapp,
                "mensaje": "Bienvenido a Catusita. Para continuar, indícame tu RUC o número de pedido.",
            }

    # Producción: consultar base de datos
    if agente_tipo == "vendedor":
        user = await models.get_user_by_whatsapp(numero_whatsapp)
        if not user:
            return {"autenticado": False, "tipo": "asesor",
                    "mensaje": "Tu número no está registrado. Contacta a tu supervisor."}
        return {**user, "autenticado": True, "asesor_id": str(user["id"])}
    else:
        return {
            "autenticado": False,
            "tipo": "cliente",
            "numero_whatsapp": numero_whatsapp,
            "mensaje": "Bienvenido. Indícame tu RUC o número de pedido.",
        }


async def identify_client_by_ruc(ruc: str) -> dict | None:
    if USE_MOCK:
        return _MOCK_CLIENTES_RUC.get(ruc)
    return await models.get_user_by_ruc(ruc)
