from shared.sap_client import sap


async def obtener_documentos(cliente_ruc: str, tipo: str = None) -> dict:
    return await sap.get_documentos(cliente_ruc, tipo=tipo)
