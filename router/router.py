"""Resolución de multiagente. Lógica pura y determinista.

    resolver(numero_remitente, session) -> Destino

El canal es WAHA, así que la señal de "por dónde entró" es la **sesión**, no un
phone_number_id (eso es de la Cloud API / Kapso, que hoy no se usa).

Dos señales, y se exigen las dos para llegar a `vendedores`:

  1. QUIÉN escribe   — el número del remitente está en el registro de asesores
  2. POR DÓNDE entra — llegó por la sesión de WAHA del número interno

Pedir las dos es a propósito. Si un asesor le escribe al número público, entra
como cliente: el canal define el alcance, no el cargo.
"""
from dataclasses import dataclass

from router import numeros


@dataclass(frozen=True)
class Destino:
    """A qué multiagente va el mensaje y por qué. El motivo se registra en el log."""

    multiagente: str          # "vendedores" | "clientes"
    perfil: dict           # identidad resuelta; para clientes va casi vacío
    motivo: str            # por qué cayó ahí — se audita


def resolver(numero_remitente: str, session: str) -> Destino:
    """Nunca lanza y nunca devuelve `vendedores` por descarte.

    Cualquier caso raro —número sin registrar, sesión desconocida, LID que no se
    pudo traducir, registro caído— termina en `clientes`.
    """
    raise NotImplementedError


def _a_clientes(motivo: str) -> Destino:
    """Salida por defecto. Todo camino dudoso pasa por acá."""
    return Destino(
        multiagente="clientes",
        perfil={"tipo": "cliente", "autenticado": False},
        motivo=motivo,
    )


# TODO al implementar `resolver`:
#   1. si el remitente viene como '<lid>@lid', traducirlo con
#      shared/waha.resolve_lid_to_phone ANTES de buscar. Si falla -> _a_clientes
#   2. numeros.normalizar(numero)
#   3. numeros.es_asesor(numero) AND numeros.es_sesion_vendedores(session)
#      -> Destino("vendedores", perfil del asesor, "asesor en sesión interna")
#   4. cualquier otro caso -> _a_clientes(<motivo específico>)
#
# El paso 3 es la ÚNICA ruta a vendedores. No agregar otra.
#
# Reemplaza a webhooks/whatsapp.py:471, que hoy dice:
#     agente_tipo = "vendedor"   # por ahora solo el canal de vendedores
# es decir, todo el que escriba al número conectado entra como asesor.
