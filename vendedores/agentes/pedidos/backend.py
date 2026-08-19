"""Acceso de `pedidos` (vendedores) a las BACKEND APIS.

    GET /pedidos/{ruc}                       qué pidió un cliente
    GET /despacho?pedido_id=|factura=        dónde está y si llegó

Los dos buscan por cosas distintas y no es un detalle: `/pedidos` va por CLIENTE
y `/despacho` va por PEDIDO o FACTURA. No hay forma de pedir «el despacho de los
pedidos de este RUC» en una sola llamada — hay que sacar los números primero.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("SAP_BASE_URL", "")
API_KEY = os.getenv("SAP_API_KEY", "")
TIMEOUT = 15.0

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


async def pedidos(cliente_ruc: str, estado: str | None = None) -> dict:
    params = {"estado": estado} if estado else None
    return await _get(f"/pedidos/{cliente_ruc}", params)


async def despacho(pedido_id: str | None = None, factura: str | None = None) -> dict:
    params: dict = {}
    if pedido_id:
        params["pedido_id"] = pedido_id
    if factura:
        params["factura"] = factura
    return await _get("/despacho", params or None)
