"""Registro de números y sesiones. La tabla que el router consulta.

El canal de WhatsApp es WAHA (self-hosted, automatiza WhatsApp Web), NO la Cloud
API oficial. Eso cambia cómo se identifica el canal:

    Kapso / Cloud API  ->  phone_number_id
    WAHA               ->  session

Una sesión de WAHA es un número de WhatsApp conectado. Para tener dos canales hay
que levantar DOS sesiones (`vendedores` y `clientes`), cada una con su número.
Hoy corre una sola, `WAHA_SESSION=default`, y por eso el webhook tiene el canal
hardcodeado a "vendedor".

Los asesores viven hoy en `shared/auth.py::_MOCK_ASESORES` (~80 números mapeados
a su `vendedor_id`), sincronizados a Postgres al arrancar desde
`main.py::_sync_vendedores`. Al migrar, ese diccionario se mueve acá.

Regla de disponibilidad: si el registro no responde, `es_asesor` devuelve False.
Un asesor sin servicio es un incidente menor; un desconocido con acceso a la
cartera es uno grave.
"""
import os

# Sesión de WAHA del número interno de asesores.
SESION_VENDEDORES = os.getenv("WAHA_SESSION_VENDEDORES", "")

# Sesión del número público. Mientras no exista, el multiagente de clientes no
# tiene por dónde entrar — que es exactamente el estado de hoy.
SESION_CLIENTES = os.getenv("WAHA_SESSION_CLIENTES", "")


def normalizar(numero: str) -> str:
    """'+51 987 654 321', '51987654321@c.us' -> '987654321'.

    OJO con los LID: WAHA entrega '<lid>@lid' para muchos contactos y hay que
    traducirlo a teléfono con `shared/waha.resolve_lid_to_phone` ANTES de buscar
    en el registro. Si esa traducción falla, el número no matchea y el mensaje
    cae a clientes — que es el lado seguro.
    """
    raise NotImplementedError


def es_asesor(numero: str) -> bool:
    """¿Este número está registrado como asesor? False ante cualquier duda.

    TODO: migrar `_MOCK_ASESORES` desde shared/auth.py.
    """
    raise NotImplementedError


def perfil_asesor(numero: str) -> dict | None:
    """Perfil del asesor: vendedor_id, asesor_id, nombre. None si no lo es."""
    raise NotImplementedError


def es_sesion_vendedores(session: str) -> bool:
    """¿El mensaje llegó por la sesión interna de WAHA?

    Si SESION_VENDEDORES no está configurada devuelve False: sin la variable no
    hay canal interno y todo entra como cliente.

    Es lo contrario de lo que hace el código actual, y a propósito. Hoy el
    webhook de WAHA tiene `agente_tipo = "vendedor"` hardcodeado, así que
    cualquiera que escriba al número conectado entra como asesor.
    """
    return bool(SESION_VENDEDORES) and str(session) == str(SESION_VENDEDORES)
