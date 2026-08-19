"""A qué multiagente entra un mensaje. Lógica pura y determinista.

    resolver(numero, session) -> Destino

── Quien decide es el padrón ──────────────────────────────────────────────────

    HGET padron 51987654321  ->  "vendedores"

Una lectura de Redis y listo. Cada multiagente publica sus números al arrancar
(ver `padron.py`), así que esa tabla en RAM es la respuesta completa a «de quién
es este número».

── El canal es una señal EXTRA, y solo si existe ──────────────────────────────

Una versión anterior exigía DOS señales: el padrón Y que el mensaje hubiera
entrado por la sesión de WAHA de ese multiagente. La idea era que el canal
definiera el alcance —un asesor escribiéndole al número público entra como
cliente, no puede sacar precio neto por ahí—.

Con TRES números conectados eso está bien. Con UNO —lo que hay hoy— es un
candado sin puerta: ninguna sesión coincide, `sesion_es_de` siempre da False y
TODO cae a `clientes`, asesores incluidos. El ruteo entero muerto por una
verificación que no verifica nada.

Así que ahora el canal solo interviene cuando hay canales de verdad: si el
mensaje entró por una sesión que OTRO multiagente declaró como suya, es un cruce
real y va al lado seguro. Mientras no haya sesiones declaradas —hoy— manda el
padrón solo, y el día que se conecten los otros dos números el aislamiento se
enciende sin tocar este archivo.

── Nunca devuelve vendedores por descarte ─────────────────────────────────────

Cualquier caso raro —número sin publicar, sesión desconocida, LID que no se pudo
traducir, Redis caído— termina en `clientes`. No hay una sola rama que llegue a
`vendedores` sin las dos señales.

Reemplaza a `webhooks/whatsapp.py:448`, que hoy dice:

    agente_tipo = "vendedor"   # por ahora solo el canal de vendedores

es decir: todo el que escriba al número conectado entra como asesor.
"""
from dataclasses import dataclass

from recepcion import numeros, padron

POR_DEFECTO = "clientes"


@dataclass(frozen=True)
class Destino:
    """A qué multiagente va y por qué. El motivo se registra en el log."""

    multiagente: str
    numero: str          # ya normalizado
    motivo: str          # por qué cayó ahí — se audita


async def resolver(numero_remitente: str, session: str) -> Destino:
    """Nunca lanza. Ante cualquier duda, `clientes`."""
    numero = numeros.normalizar(numero_remitente)
    if not numero:
        return Destino(POR_DEFECTO, "", "no se pudo normalizar el número")

    dueno, motivo = await padron.multiagente_de(numero)

    if dueno == POR_DEFECTO:
        return Destino(POR_DEFECTO, numero, motivo)

    # ¿El mensaje entró por un canal que otro multiagente reclama como suyo?
    # Solo entonces el canal pesa. Si nadie declaró esa sesión —hoy, con un
    # único número— esto da "" y manda el padrón.
    canal = numeros.multiagente_de_sesion(session)
    if canal and canal != dueno:
        return Destino(
            POR_DEFECTO, numero,
            f"el padrón dice {dueno} pero escribió al número de {canal}",
        )

    return Destino(dueno, numero, motivo)
