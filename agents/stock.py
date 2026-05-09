from shared.sap_client import sap


async def consultar_stock(sku_code: str, almacen_id: int = 0) -> dict:
    result = await sap.get_stock(sku_code, almacen_id)
    if "error" in result:
        return result
    result["almacen_miraflores_nombre"] = "Almacén Miraflores"
    result["almacen_ate_nombre"] = "Almacén Ate"
    return result


async def consultar_reposicion(sku_code: str) -> dict:
    return await sap.get_restock_date(sku_code)


async def consultar_antiguedad(almacen_id: int = 0, dias_minimos: int = 90) -> dict:
    return await sap.get_stock_aging(almacen_id, dias_minimos)
