"""Área `clientes` de Vendedores — Clientes y cartera.

Contesta: ¿Quién es este cliente y está en mi cartera?
Entidad:  RUC

    EXPONE datos sensibles:
      - cartera completa del asesor
      - datos comerciales del cliente

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Vendedores importa código de
Clientes.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      (se basta con lo suyo)
"""
from vendedores.agentes.clientes.agente import NODO
from vendedores.agentes.clientes.tools import TOOLS

# resolución de entidades sobre una lista acotada
MODELO = "claude-haiku-4-5-20251001"

# lookup contra el backend, responde en segundos
# Su cola propia. La consume SU servicio, nadie más.
COLA = "v:clientes"

__all__ = ["MODELO", "COLA", "NODO", "TOOLS"]
