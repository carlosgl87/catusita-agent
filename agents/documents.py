from shared.sap_client import sap
from agents import orders


async def obtener_documentos(cliente_ruc: str, tipo: str = None) -> dict:
    return await sap.get_documentos(cliente_ruc, tipo=tipo)


def _norm_num(s: str) -> str:
    return (s or "").replace(" ", "").replace("/", "").upper()


async def enviar_documento(cliente_ruc: str, numero_documento: str) -> dict:
    """Devuelve el PDF (base64) de una factura o nota de crédito de un cliente.

    El buscador de documentos electrónicos exige el N° + su tipo (01/07) + la empresa
    (04/01). El agente solo conoce el N° y el cliente, así que primero se buscan los
    pedidos del cliente y ahí se ubica el documento (con sus códigos) antes de descargar.
    """
    ped = await orders.consultar_pedidos(cliente_ruc)
    if not ped or ped.get("error"):
        return {"error": "SIN_PEDIDOS",
                "mensaje": "No pude obtener los pedidos del cliente para ubicar el documento."}

    objetivo = _norm_num(numero_documento)
    encontrado = None
    for p in ped.get("pedidos", []) or []:
        for d in p.get("documentos", []) or []:
            if _norm_num(d.get("numero")) == objetivo:
                encontrado = d
                break
            for nc in d.get("notas_credito", []) or []:
                if _norm_num(nc.get("numero")) == objetivo:
                    encontrado = nc
                    break
            if encontrado:
                break
        if encontrado:
            break

    if not encontrado:
        return {"error": "DOC_NO_ENCONTRADO",
                "mensaje": (f"No encontré el documento {numero_documento} en los pedidos "
                            "de ese cliente. Verifica el número o el cliente.")}

    return await sap.get_documento(
        numero=encontrado.get("numero"),
        tipo=encontrado.get("tipo_codigo") or "01",
        empresa=encontrado.get("empresa_codigo") or "04",
    )
