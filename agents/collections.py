from datetime import datetime
from shared.sap_client import sap


async def consultar_letras_proximas(asesor_id: str, dias: int = 7) -> dict:
    data = await sap.get_collections_report(asesor_id)
    if "error" in data:
        return data
    hoy = datetime.now().date()
    proximas = [
        l for l in data.get("letras", [])
        if -7 <= l.get("dias_vcto", 999) <= dias
    ]
    return {
        "asesor": data.get("asesor_nombre"),
        "letras_proximas": proximas,
        "total_monto": sum(l["monto"] for l in proximas),
    }


async def reporte_cobranzas(asesor_id: str, semana: str = None) -> dict:
    return await sap.get_collections_report(asesor_id, semana)
