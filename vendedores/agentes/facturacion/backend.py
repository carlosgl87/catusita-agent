"""Acceso de `facturacion` (vendedores) a las BACKEND APIS.

    GET /documento?numero=&tipo=&empresa=          el PDF
    GET /documento/pagos?numero=&tipo=&empresa=    cómo se pagó
    GET /pedidos/{ruc}                             para ubicar el documento

── Por qué esta área llama a /pedidos ─────────────────────────────────────────

Los dos primeros endpoints exigen `numero + tipo + empresa`. El asesor solo sabe
el número («mandame la F001-0102835»). Los otros dos códigos únicamente aparecen
dentro de los pedidos del cliente.

No es hablarle al ÁREA `pedidos` — es usar un endpoint para resolver sus propios
identificadores. Lo que el diseño prohíbe es que un área le PIDA algo a otra;
acá no hay nadie del otro lado.

Dicho eso: «para bajar una factura primero hay que ubicarla en los pedidos» es
un PROCEDIMIENTO, y su lugar natural es el RAG de procesos, no este docstring.
Cuando `conocimiento` tenga contenido cargado, esto se mueve allá.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("SAP_BASE_URL", "")
API_KEY = os.getenv("SAP_API_KEY", "")
TIMEOUT = 15.0

# `/documento` descarga un PDF entero.
TIMEOUT_DESCARGA = 30.0

_cliente: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _cliente
    if _cliente is None:
        if not BASE_URL:
            raise RuntimeError("Falta SAP_BASE_URL.")
        _cliente = httpx.AsyncClient(
            base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=TIMEOUT)
    return _cliente


async def _get(path: str, params: dict | None = None, timeout: float | None = None) -> dict:
    try:
        kwargs: dict = {"params": params}
        if timeout is not None:
            kwargs["timeout"] = timeout
        r = await _http().get(path, **kwargs)
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


def _norm(s: str) -> str:
    """F001-0102835, f001 0102835, F001/0102835 -> todos al mismo string.

    El asesor lo escribe de memoria y cada uno usa un separador distinto.
    """
    return (s or "").replace(" ", "").replace("/", "").replace("-", "").upper()


async def ubicar(cliente_ruc: str, numero: str) -> dict:
    """Encuentra el documento entre los pedidos del cliente y devuelve sus
    códigos (`tipo_codigo`, `empresa_codigo`). `{"error": ...}` si no está.

    Busca también dentro de las notas de crédito de cada documento: una NC tiene
    su propio número y el asesor la pide igual que una factura.
    """
    ped = await _get(f"/pedidos/{cliente_ruc}")
    if not ped or ped.get("error"):
        return {"error": "SIN_PEDIDOS",
                "mensaje": "No se pudieron leer los pedidos del cliente."}

    buscado = _norm(numero)
    for p in ped.get("pedidos") or []:
        for d in p.get("documentos") or []:
            if _norm(d.get("numero")) == buscado:
                return d
            for nc in d.get("notas_credito") or []:
                if _norm(nc.get("numero")) == buscado:
                    return nc

    return {"error": "DOC_NO_ENCONTRADO",
            "mensaje": (f"El documento {numero} no aparece en los pedidos de ese "
                        "cliente. Verificá el número o el cliente.")}


async def pdf(numero: str, tipo: str, empresa: str) -> dict:
    return await _get("/documento",
                      {"numero": numero, "tipo": tipo, "empresa": empresa},
                      timeout=TIMEOUT_DESCARGA)


async def pagos(numero: str, tipo: str, empresa: str) -> dict:
    return await _get("/documento/pagos",
                      {"numero": numero, "tipo": tipo, "empresa": empresa},
                      timeout=20.0)
