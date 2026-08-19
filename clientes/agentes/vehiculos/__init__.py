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

# la consulta de placa tarda 30-60s

# Lo que el orquestador ve de esta área. Es la PREGUNTA que contesta, no
# la lista de sus tools: el orquestador delega en el ÁREA y es ella la que
# decide cuáles usar y en qué orden.
DESCRIPCION = (
    "Qué vehículo es una placa peruana: marca, modelo, año, VIN y motor. TARDA 30-60 SEGUNDOS."
)

__all__ = ["MODELO", "DESCRIPCION", "NODO", "TOOLS"]
