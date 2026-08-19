"""Acceso de `productos` (clientes) a las BACKEND APIS.

Esta área es dueña de su acceso: sus endpoints, su timeout y su mapeo.
Es un archivo distinto del de `vendedores`, aunque peguen al mismo endpoint.

LÍMITE DE ESTE BACKEND — no es una omisión, es la frontera:
    NO mapea precio_neto y descuentos — este backend NO mapea ese campo
    NO mapea almacén y ubicación física — tampoco se mapea

    Endpoints:
      - GET /stock/{sku}
      - GET /precios/{sku}
      - GET /imagen/{sku}
      - GET /catalogo
"""
import os

import httpx

BASE_URL = os.getenv("SAP_BASE_URL", "")
API_KEY = os.getenv("SAP_API_KEY", "")
TIMEOUT = 10.0


async def _get(path: str, params: dict | None = None) -> dict:
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(f"{BASE_URL}{path}", params=params, headers=headers)
        r.raise_for_status()
        return r.json()


# TODO: una función por endpoint, mapeando SOLO los campos permitidos.
