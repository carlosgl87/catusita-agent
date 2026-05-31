from shared.sap_client import sap


async def consultar_credito(cliente_ruc: str) -> dict:
    return await sap.get_credito(cliente_ruc)


async def consultar_historial(cliente_ruc: str, meses: int = 18) -> dict:
    return await sap.get_historial(cliente_ruc, meses=meses)
