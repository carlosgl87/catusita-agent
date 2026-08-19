"""Router. Decide a qué multiagente entra un mensaje: vendedores o clientes.

Está ARRIBA de los dos supervisores. Kapso entra por un solo webhook, el router
resuelve quién escribe y recién ahí se invoca el grafo que corresponde.

Es LÓGICO, no un LLM. Conoce los números y hace una búsqueda; no interpreta ni
razona. Tres motivos:

  - un LLM que se equivoca acá le da acceso a precio neto y cartera a alguien
    de afuera. Esa decisión no se delega a un modelo
  - tarda microsegundos y no cuesta tokens
  - se puede testear exhaustivamente: es una tabla

FALLA CERRADO. Si el número no está en el registro de asesores, el mensaje va a
`clientes`, que es el multiagente que menos ve. Nunca al revés.

Esa regla existe porque la versión anterior hacía exactamente lo contrario:

    def _resolver_agente_tipo(phone_number_id):
        if KAPSO_PHONE_NUMBER_ID_CLIENTES and ...:
            return "cliente"
        return "vendedor"        # <- default al lado privilegiado

Con esa forma, una env var sin poner mandaba a todo el mundo al agente de
vendedores.
"""
from router.router import Destino, resolver

__all__ = ["Destino", "resolver"]
