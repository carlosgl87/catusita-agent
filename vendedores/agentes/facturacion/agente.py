"""Subgrafo de `facturacion` (vendedores).

Nodo del grafo de Vendedores, con estado propio. Sus mensajes internos no
suben al historial: al orquestador solo le llega el resultado.

Salidas permitidas (las fuerza vendedores/grafo.py):
  - SOLO vuelve a `supervisor`
  - NO va a otra área
  - NO va a END: toda respuesta pasa por `validar`

Si le falta un dato de otra área NO la llama: termina su turno
diciendo qué necesita, y el orquestador decide.

    falta cuando le dan un RUC pero no el N° de documento
      -> lo tiene `pedidos`
"""
from vendedores.agentes.facturacion.prompt import SYSTEM  # noqa: F401
from vendedores.agentes.facturacion.tools import TOOLS  # noqa: F401

NODO = None  # TODO: StateGraph propio, compilado con MODELO y TOOLS
