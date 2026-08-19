"""Área `facturacion` de Vendedores — Facturación.

Contesta: ¿Está pagada? Mándame el PDF.
Entidad:  documento

    EXPONE datos sensibles:
      - estado de deuda y letras de un documento

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Vendedores importa código de
Clientes.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      - `pedidos` — cuando le dan un RUC pero no el N° de documento
"""
from vendedores.agentes.facturacion.agente import NODO
from vendedores.agentes.facturacion.tools import TOOLS

# lookup de documento y formateo
MODELO = "claude-haiku-4-5-20251001"

# lookup contra el backend, responde en segundos

__all__ = ["MODELO", "NODO", "TOOLS"]
