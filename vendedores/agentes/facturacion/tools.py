"""Tools de `facturacion` (vendedores): el PDF y el estado de pago.

Las dos hacen el mismo par de pasos antes de tocar su endpoint: verificar que el
cliente sea de la cartera, y ubicar el documento entre sus pedidos. Ese par está
en `_resolver` porque si una de las dos se lo saltara, el control de acceso
tendría un agujero del tamaño de una tool.
"""
import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from vendedores.agentes.facturacion import backend
from vendedores.plataforma_vendedores import acceso


def _responder(resultado: dict, tool_call_id: str, extra: dict | None = None) -> Command:
    update: dict = {"messages": [ToolMessage(
        content=json.dumps(resultado, ensure_ascii=False, default=str),
        tool_call_id=tool_call_id)]}
    if extra:
        update.update(extra)
    return Command(update=update)


async def _resolver(cliente: str, numero: str, perfil: dict):
    """Cartera -> documento. Devuelve (doc, None) o (None, error)."""
    ruc, error = await acceso.verificar(cliente, perfil)
    if error:
        return None, error
    doc = await backend.ubicar(ruc, numero)
    if doc.get("error"):
        return None, doc
    return doc, None


@tool
async def enviar_documento(
    cliente: str,
    numero_documento: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Manda el PDF de una FACTURA o NOTA DE CRÉDITO al chat de WhatsApp.

    Necesita el cliente (RUC o nombre) y el número del documento (ej.
    F001-0102835). Solo facturas y notas de crédito — guías de remisión no.

    El PDF se manda solo: en el texto solo confirmá que se envió."""
    doc, error = await _resolver(cliente, numero_documento, state.get("perfil") or {})
    if error:
        return _responder(error, tool_call_id)

    resultado = await backend.pdf(
        doc.get("numero"),
        doc.get("tipo_codigo") or "01",
        doc.get("empresa_codigo") or "04",
    )

    if not resultado or resultado.get("error") or not resultado.get("pdf_base64"):
        return _responder(resultado or {
            "error": "SIN_DOCUMENTO",
            "mensaje": f"No se pudo descargar el documento {numero_documento}.",
        }, tool_call_id)

    numero = resultado.get("numero", numero_documento)
    tipo = resultado.get("tipo", "documento")
    media = [{
        "documento_base64": resultado["pdf_base64"],
        "caption": f"{tipo} {numero}",
        "filename": resultado.get("filename", f"{numero}.pdf"),
        "mime": resultado.get("mime", "application/pdf"),
    }]
    return _responder(
        {"numero": numero, "tipo": tipo, "cliente": resultado.get("cliente", ""),
         "mensaje": f"Se envió el PDF de {tipo} {numero} al chat."},
        tool_call_id,
        {"media_pendiente": media},
    )


@tool
async def consultar_pago_documento(
    cliente: str,
    numero_documento: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Si una factura o NC está pagada: saldo pendiente, si se pagó con LETRAS
    (canje) o con NOTA DE CRÉDITO, y el detalle de los pagos.

    Para «¿está pagada?», «¿se pagó con letras?», «¿cuánto debe de esa factura?».
    NO descarga el PDF — para eso está enviar_documento."""
    doc, error = await _resolver(cliente, numero_documento, state.get("perfil") or {})
    if error:
        return _responder(error, tool_call_id)

    resultado = await backend.pagos(
        doc.get("numero"),
        doc.get("tipo_codigo") or "01",
        doc.get("empresa_codigo") or "04",
    )
    return _responder(resultado or {
        "error": "SIN_DATO",
        "mensaje": f"No se pudo leer el estado de pago de {numero_documento}.",
    }, tool_call_id)


TOOLS = [enviar_documento, consultar_pago_documento]
