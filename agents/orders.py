from shared.sap_client import sap


async def consultar_pedido(pedido_id: str = None, ruc_cliente: str = None) -> dict:
    return await sap.get_order_status(pedido_id, ruc_cliente)


async def consultar_almacen_producto(sku_code: str) -> dict:
    result = await sap.get_stock(sku_code, almacen_id=0)
    if "error" in result:
        return result
    return {
        "sku_code": result["sku_code"],
        "descripcion": result["descripcion"],
        "disponible_miraflores": result["almacen_miraflores"],
        "disponible_ate": result["almacen_ate"],
        "total": result["total"],
    }
