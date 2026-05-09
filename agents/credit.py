from shared.sap_client import sap


async def consultar_credito(cliente_id: str) -> dict:
    return await sap.get_credit(cliente_id)
