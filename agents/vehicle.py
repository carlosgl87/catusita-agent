from shared.sap_client import sap


async def identificar_vehiculo(placa_o_vin: str) -> dict:
    """
    Acepta placa (formato ABC-123) o VIN (17 caracteres).
    El mock SAP detecta automáticamente cuál es cuál.
    """
    if not placa_o_vin:
        return {"error": "Se requiere placa o VIN"}
    return await sap.get_vehiculo(placa_o_vin)
