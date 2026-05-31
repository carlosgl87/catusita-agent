from shared.sap_client import sap


async def consultar_cobranzas(cliente_ruc: str, estado: str = None) -> dict:
    """
    estado puede ser: 'pendiente', 'vencida', 'pagada'
    """
    return await sap.get_cobranzas(cliente_ruc, estado=estado)


async def consultar_letras_proximas(cliente_ruc: str) -> dict:
    """Obtiene letras pendientes y vencidas del cliente."""
    result = await sap.get_cobranzas(cliente_ruc)
    if "error" in result:
        return result
    letras = result.get("letras", [])
    proximas = [l for l in letras if l.get("estado") in ("pendiente", "vencida")]
    return {
        "cliente_ruc": cliente_ruc,
        "total_deuda": result.get("total_deuda", 0),
        "deuda_vencida": result.get("deuda_vencida", 0),
        "letras_activas": proximas,
    }
