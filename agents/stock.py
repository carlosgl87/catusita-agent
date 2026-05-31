from shared.sap_client import sap


async def consultar_stock(sku_code: str) -> dict:
    result = await sap.get_stock(sku_code)
    if "error" in result:
        return result
    return result


async def buscar_productos(q: str = None, categoria: str = None,
                            marca: str = None, solo_con_stock: bool = False) -> dict:
    return await sap.get_catalogo(q=q, categoria=categoria,
                                   marca=marca, con_stock=solo_con_stock if solo_con_stock else None)
