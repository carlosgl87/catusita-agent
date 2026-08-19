"""El único endpoint que `acceso` necesita: la cartera del asesor.

    GET /vendedor/{id}/clientes

Está separado del backend del área `clientes` a propósito, aunque llame al mismo
endpoint. Si `acceso` importara el backend del área, la política de seguridad del
multiagente dependería de un área — y cambiar esa área podría romper el control
de acceso de las otras dos sin que nadie lo note.

Son ~20 líneas duplicadas. Se pagan a gusto por no acoplar la política a un área.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("SAP_BASE_URL", "")
API_KEY = os.getenv("SAP_API_KEY", "")
TIMEOUT = 10.0

_cliente: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _cliente
    if _cliente is None:
        if not BASE_URL:
            raise RuntimeError("Falta SAP_BASE_URL.")
        _cliente = httpx.AsyncClient(
            base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=TIMEOUT
        )
    return _cliente


async def cartera(vendedor_id: str) -> dict:
    """Clientes asignados al asesor. Lanza si falla: quien llama decide.

    `acceso.py` atrapa la excepción y falla cerrado. Devolver `{}` en silencio
    haría que una caída del backend se viera igual que «no tenés clientes», y
    eso autorizaría de menos sin que nadie entienda por qué.
    """
    if not vendedor_id:
        return {"clientes": []}
    r = await _http().get(f"/vendedor/{vendedor_id}/clientes")
    r.raise_for_status()
    return r.json()
