import os
import httpx
from dotenv import load_dotenv

load_dotenv()

PLACA_URL = os.getenv("PLACA_API_URL", "")
PLACA_KEY = os.getenv("PLACA_API_KEY", "")

# Mock de vehículos por placa para desarrollo
_MOCK_VEHICLES = {
    "ABC-123": {"marca": "Toyota", "modelo": "Hilux", "anio": 2019, "motor": "2GD-FTV 2.4D",
                "combustible": "Diesel", "vin": "MR0FR22G900123456"},
    "XYZ-789": {"marca": "Hyundai", "modelo": "H1", "anio": 2020, "motor": "D4CB 2.5D",
                "combustible": "Diesel", "vin": "KMHWH81HPKU789012"},
    "DEF-456": {"marca": "Nissan", "modelo": "Frontier", "anio": 2018, "motor": "YD25DDTi 2.5D",
                "combustible": "Diesel", "vin": "JN1TAND20Z0456789"},
    "GHI-321": {"marca": "Toyota", "modelo": "Corolla", "anio": 2021, "motor": "2ZR-FE 1.8",
                "combustible": "Gasolina", "vin": "JTDEPRAE5LJ321654"},
}


async def identificar_vehiculo(placa: str = None, vin: str = None) -> dict:
    if not placa and not vin:
        return {"error": "Se requiere placa o VIN"}

    if os.getenv("USE_SAP_MOCK", "true").lower() == "true":
        if placa:
            placa_norm = placa.upper().replace(" ", "")
            v = _MOCK_VEHICLES.get(placa_norm)
            if v:
                return {"placa": placa_norm, **v}
            return {"error": f"Placa {placa} no encontrada en el sistema"}
        if vin:
            for placa_k, v in _MOCK_VEHICLES.items():
                if v.get("vin") == vin:
                    return {"placa": placa_k, **v}
            return {"error": f"VIN {vin} no encontrado"}

    async with httpx.AsyncClient(timeout=8.0) as client:
        params = {"key": PLACA_KEY}
        if placa:
            resp = await client.get(f"{PLACA_URL}/placa/{placa}", params=params)
        else:
            resp = await client.get(f"{PLACA_URL}/vin/{vin}", params=params)
        resp.raise_for_status()
        return resp.json()
