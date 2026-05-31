from shared.sap_client import sap


async def consultar_pedidos(cliente_ruc: str, estado: str = None) -> dict:
    return await sap.get_pedidos(cliente_ruc, estado=estado)
