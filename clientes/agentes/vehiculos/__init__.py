"""Área `vehiculos` de Clientes — Vehículos.

Contesta: ¿Qué auto es y qué le sirve?
Entidad:  placa / VIN

    NO EXPONE (y no puede: el código no mapea esos campos):
      - propietario registral — es dato personal de un tercero, este backend NO lo mapea
      - partidas registrales

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Clientes importa código de
Vendedores.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      (se basta con lo suyo)
"""
from clientes.agentes.vehiculos.agente import NODO
from clientes.agentes.vehiculos.tools import TOOLS

# lee con visión la tarjeta vehicular
MODELO = "claude-sonnet-5"

# SUNARP tarda 20-60s y se cuelga
# Su cola propia. La consume SU servicio, nadie más.
COLA = "c:vehiculos"

__all__ = ["MODELO", "COLA", "NODO", "TOOLS"]
