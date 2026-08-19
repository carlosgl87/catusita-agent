"""Acceso de `clientes` (vendedores) a las BACKEND APIS.

    GET /vendedor/{id}/clientes   la cartera del asesor
    GET /clientes/{ruc}           el perfil de uno

Ojo: `plataforma_vendedores/backend_cartera.py` llama al mismo primer endpoint.
No es un descuido — está duplicado a propósito. Aquel lo usa el control de
acceso, que es una política del multiagente; si dependiera de este archivo, un
cambio en esta área podría romper el control de acceso de `pedidos` y
`facturacion` sin que nadie lo note.
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
            base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=TIMEOUT)
    return _cliente


async def _get(path: str, params: dict | None = None) -> dict:
    try:
        r = await _http().get(path, params=params)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": "NO_ENCONTRADO", "mensaje": f"No existe: {path}"}
        return {"error": f"Error del servidor: {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "La consulta tardó demasiado."}
    except httpx.RequestError:
        return {"error": "No se pudo conectar al servidor."}


async def cartera(vendedor_id: str, estado: str | None = None,
                  tipo: str | None = None) -> dict:
    params = {}
    if estado:
        params["estado"] = estado
    if tipo:
        params["tipo"] = tipo
    return await _get(f"/vendedor/{vendedor_id}/clientes", params or None)


async def perfil(ruc: str) -> dict:
    return await _get(f"/clientes/{ruc}")
