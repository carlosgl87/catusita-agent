from shared.sap_client import sap


async def consultar_placa_sunarp(placa: str, imagen: bool = True) -> dict:
    """
    Consulta oficial en SUNARP por placa peruana.

    Devuelve datos del vehículo (marca, modelo, año, color, VIN, motor,
    estado, propietario), partida(s) registral(es) y la foto de la tarjeta
    de identificación vehicular en `imagen_base64`. La consulta tarda ~20-60s.

    NOTA: el `imagen_base64` (~150 KB) NO debe llegar al LLM. El router
    (execute_tool) lo extrae y lo encola para enviarlo por WhatsApp, dejando
    al modelo solo los datos de texto.
    """
    if not placa:
        return {"error": "Se requiere la placa del vehículo"}

    return await sap.get_placa(placa.strip().upper(), imagen=imagen)
