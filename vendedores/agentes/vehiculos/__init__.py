"""Área `vehiculos` de Vendedores — Vehículos.

Contesta: ¿Qué auto es esta placa?
Entidad:  placa / VIN

    EXPONE datos sensibles:
      - propietario registral del vehículo
      - partidas registrales

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Vendedores importa código de
Clientes.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      (se basta con lo suyo)
"""
from vendedores.agentes.vehiculos.agente import NODO
from vendedores.agentes.vehiculos.tools import TOOLS

# lee con visión la tarjeta de identificación vehicular
MODELO = "claude-sonnet-5"

# SUNARP tarda 20-60s y se cuelga; YAHUAR es un relay bloqueante

__all__ = ["MODELO", "NODO", "TOOLS"]
