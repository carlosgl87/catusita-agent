from shared.sap_client import sap


async def consultar_precio(sku_code: str, tipo_cliente: str,
                            asesor_id: str = None, cantidad: int = 1,
                            zona: str = None) -> dict:
    return await sap.get_prices(sku_code, tipo_cliente, asesor_id, cantidad, zona)
