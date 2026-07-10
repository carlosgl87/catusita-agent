import os
from db import models

USE_MOCK = os.getenv("USE_AUTH_MOCK", "true").lower() == "true"

# SellerId real de Catusita que se usa como cartera de PRUEBA mientras no exista el
# mapeo definitivo número_WhatsApp -> SellerId (ver docs/vendedores_directorio.md).
# Default "2" = "Tarazona Davila Jefer" (85 clientes). NUNCA usar "1" (bucket Gerencia,
# devuelve los 3579 clientes de toda la empresa).
SELLER_ID_DEMO = os.getenv("SELLER_ID_DEMO", "2")

# Usuarios mock para desarrollo sin base de datos
_MOCK_ASESORES = {
    "51987654321": {
        "user_id": "asesor-001",
        "tipo": "asesor",
        "nombre": "Luis García",
        "linea_asignada": "filtros y lubricantes",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-001",
        "vendedor_id": SELLER_ID_DEMO,   # ← ID que usa el Mock SAP Server
        "autenticado": True,
    },
    "51912345678": {
        "user_id": "asesor-002",
        "tipo": "asesor",
        "nombre": "María Torres",
        "linea_asignada": "frenos y suspensión",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-002",
        "vendedor_id": SELLER_ID_DEMO,   # ← ID que usa el Mock SAP Server
        "autenticado": True,
    },
    "51940351180": {
        "user_id": "asesor-003",
        "tipo": "asesor",
        "nombre": "Gabriel Cánepa",
        "linea_asignada": "filtros y lubricantes",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-003",
        "vendedor_id": SELLER_ID_DEMO,   # ← cartera con datos de QA (Transportes Andinos, etc.)
        "autenticado": True,
    },
    "51979405331": {
        "user_id": "asesor-004",
        "tipo": "asesor",
        "nombre": "Carlos Gamero",
        "linea_asignada": "filtros y lubricantes",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-004",
        "vendedor_id": SELLER_ID_DEMO,   # ← cartera con datos de QA (Transportes Andinos, etc.)
        "autenticado": True,
    },
    "51941310500": {
        "user_id": "asesor-005",
        "tipo": "asesor",
        "nombre": "Gabriel Villanueva",
        "linea_asignada": "filtros y lubricantes",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-005",
        "vendedor_id": SELLER_ID_DEMO,   # ← cartera con datos de QA
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


def _asesor_sandbox(numero_whatsapp: str) -> dict:
    """Perfil de asesor por defecto para el sandbox: en Kapso quien escribe en el
    canal de vendedores ES un asesor de ventas, aunque su celular no esté en la
    lista mock. Se mapea a V001 (la cartera con datos de QA)."""
    return {
        "user_id": f"asesor-sandbox-{numero_whatsapp}",
        "tipo": "asesor",
        "nombre": "Luis García",
        "linea_asignada": "filtros y lubricantes",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-001",
        "vendedor_id": SELLER_ID_DEMO,
        "whatsapp_number": numero_whatsapp,
        "autenticado": True,
    }


async def get_user_profile(numero_whatsapp: str, agente_tipo: str) -> dict:
    if USE_MOCK:
        if agente_tipo == "vendedor":
            # Número conocido → su perfil; cualquier otro → asesor sandbox (V001).
            return _MOCK_ASESORES.get(numero_whatsapp) or _asesor_sandbox(numero_whatsapp)
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
