from shared.sap_client import sap


async def buscar_catalogo(query: str, placa: str = None, vin: str = None) -> dict:
    """
    Busca productos en el catálogo.
    Si se proporciona placa o VIN, primero identifica el vehículo
    y luego busca repuestos compatibles.
    """
    vehiculo = None

    if placa or vin:
        placa_o_vin = placa or vin
        vehiculo_result = await sap.get_vehiculo(placa_o_vin)
        if "error" not in vehiculo_result:
            vehiculo = vehiculo_result
            # Si hay repuestos_compatibles en la respuesta del vehículo, usarlos directamente
            if vehiculo_result.get("repuestos_compatibles"):
                return {
                    "query": query,
                    "vehiculo": vehiculo,
                    "resultados": vehiculo_result["repuestos_compatibles"],
                    "total": len(vehiculo_result["repuestos_compatibles"]),
                }

    # Búsqueda en catálogo por texto
    result = await sap.get_catalogo(q=query)
    return {
        "query": query,
        "vehiculo": vehiculo,
        "resultados": result.get("productos", []),
        "total": result.get("total", 0),
    }
