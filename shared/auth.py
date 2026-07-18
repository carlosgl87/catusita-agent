import os
from db import models

USE_MOCK = os.getenv("USE_AUTH_MOCK", "true").lower() == "true"

# SellerId real de Catusita que se usa como cartera de PRUEBA mientras no exista el
# mapeo definitivo número_WhatsApp -> SellerId (ver docs/vendedores_directorio.md).
# Default "2" = "Tarazona Davila Jefer" (85 clientes). NUNCA usar "1" (bucket Gerencia,
# devuelve los 3579 clientes de toda la empresa).
SELLER_ID_DEMO = os.getenv("SELLER_ID_DEMO", "2")

# Si es true, cualquier número no registrado se autentica como el vendedor demo
# (modo prueba abierto). Por defecto FALSE: a un número no registrado NO se le da
# acceso ni datos — se le pide que se registre. Ver incidencia #11.
ALLOW_SANDBOX_AUTH = os.getenv("ALLOW_SANDBOX_AUTH", "false").lower() == "true"

# Vendedores reales de prueba: cada número de WhatsApp mapeado a su SellerId real
# de Catusita (ver docs/vendedores_directorio.md). El vendedor_id es el SellerId
# que se pasa a /vendedor/{id}/clientes para traer SU cartera.
_MOCK_ASESORES = {
    "51958133722": {
        "user_id": "asesor-28",
        "tipo": "asesor",
        "nombre": "Saavedra Cicirello Jose Domingo",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0051",
        "vendedor_id": "28",   # 294 clientes
        "autenticado": True,
    },
    "51956646145": {
        "user_id": "asesor-28",
        "tipo": "asesor",
        "nombre": "Saavedra Cicirello Jose Domingo",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0051",
        "vendedor_id": "28",   # 294 clientes (2do número de Saavedra)
        "autenticado": True,
    },
    "51948985984": {
        "user_id": "asesor-50",
        "tipo": "asesor",
        "nombre": "Revolledo Humala Paulo",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0037",
        "vendedor_id": "50",   # 274 clientes
        "autenticado": True,
    },
    "51917842636": {
        "user_id": "asesor-78",
        "tipo": "asesor",
        "nombre": "Lupuche Morante Patricia Veronica",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0021",
        "vendedor_id": "78",   # 216 clientes
        "autenticado": True,
    },
    "51998321666": {
        "user_id": "asesor-53",
        "tipo": "asesor",
        "nombre": "Quispe Tasa William",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0009",
        "vendedor_id": "53",   # 186 clientes
        "autenticado": True,
    },
    "51960189568": {
        "user_id": "asesor-22",
        "tipo": "asesor",
        "nombre": "Peña Alva Mariluz Milagros",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0043",
        "vendedor_id": "22",   # 184 clientes
        "autenticado": True,
    },
    "51940351180": {
        "user_id": "asesor-58",
        "tipo": "asesor",
        "nombre": "Osorio Echevarria Roger Alcides",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0074",
        "vendedor_id": "58",   # 171 clientes
        "autenticado": True,
    },
    "51979405331": {
        "user_id": "asesor-29",
        "tipo": "asesor",
        "nombre": "Escobar Herrera Stephanny",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0052",
        "vendedor_id": "29",   # 163 clientes
        "autenticado": True,
    },
    # ── Lote 2: pares número↔vendedor confirmados con el directorio real ──────
    "51960660141": {
        "user_id": "asesor-56",
        "tipo": "asesor",
        "nombre": "Aparco Aparco Stefany Katherin",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0068",
        "vendedor_id": "56",   # 26 clientes
        "autenticado": True,
    },
    "51993819074": {
        "user_id": "asesor-60",
        "tipo": "asesor",
        "nombre": "Pinedo Peña Luz",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0012",
        "vendedor_id": "60",   # 67 clientes
        "autenticado": True,
    },
    "51932724126": {
        "user_id": "asesor-78",
        "tipo": "asesor",
        "nombre": "Lupuche Morante Patricia Veronica",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0021",
        "vendedor_id": "78",   # 216 clientes
        "autenticado": True,
    },
    "51922553756": {
        "user_id": "asesor-16",
        "tipo": "asesor",
        "nombre": "Chavez Ariste Fernando",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0032",
        "vendedor_id": "16",   # 144 clientes
        "autenticado": True,
    },
    "51986159395": {
        "user_id": "asesor-76",
        "tipo": "asesor",
        "nombre": "Vega Ganoza Jose Carlos",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0030",
        "vendedor_id": "76",   # 102 clientes
        "autenticado": True,
    },
    "51925240250": {
        "user_id": "asesor-66",
        "tipo": "asesor",
        "nombre": "Cardoza Lara Tamara Beatriz",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0022",
        "vendedor_id": "66",   # 134 clientes
        "autenticado": True,
    },
    # 'Alonso Salgado' no existe en el directorio de Catusita. Se le asigna esta
    # cartera porque el cliente que consultó (Contratistas Generales Cáceres) es
    # justamente de ella — así su consulta real funciona. Reasignar cuando se
    # confirme su código de vendedor verdadero.
    "51912263095": {
        "user_id": "asesor-52",
        "tipo": "asesor",
        "nombre": "Lupaca Castañeda Gisela Yanet",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0055",
        "vendedor_id": "52",   # 72 clientes
        "autenticado": True,
    },

    # ── LIDs ──────────────────────────────────────────────────────────────────
    # WAHA entrega para algunos contactos el LID interno de Meta ('<lid>@lid') en
    # vez del teléfono. Ese LID es estable por cuenta, así que se mapea igual que
    # un número. Se captura de los logs: [WAHA] from='<lid>@lid'.
    "111621938671767": {   # LID de Gabriel (tel 51940351180) → Osorio
        "user_id": "asesor-58",
        "tipo": "asesor",
        "nombre": "Osorio Echevarria Roger Alcides",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "0074",
        "vendedor_id": "58",   # 171 clientes
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
        "nombre": "Asesor Catusita",
        "linea_asignada": "",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-DEMO",
        "vendedor_id": SELLER_ID_DEMO,
        "whatsapp_number": numero_whatsapp,
        "autenticado": True,
    }


async def get_user_profile(numero_whatsapp: str, agente_tipo: str) -> dict:
    if USE_MOCK:
        if agente_tipo == "vendedor":
            # Número conocido → su perfil.
            perfil = _MOCK_ASESORES.get(numero_whatsapp)
            if perfil:
                return perfil
            # No registrado: solo en modo prueba abierto se le da la cartera demo.
            if ALLOW_SANDBOX_AUTH:
                return _asesor_sandbox(numero_whatsapp)
            # Por defecto: no autenticar ni dar datos a un número desconocido.
            return {
                "autenticado": False,
                "tipo": "asesor",
                "numero_whatsapp": numero_whatsapp,
                "mensaje": ("Tu número no está registrado en el sistema. "
                            "Por favor contacta a tu supervisor para que te den de alta."),
            }
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
