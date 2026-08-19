"""Acceso de `productos` (vendedores) a las BACKEND APIS.

Cuatro endpoints y ninguno más:

    GET /stock/{sku}        cuánto hay
    GET /precios/{sku}      cuánto vale
    GET /catalogo?q=        qué existe
    GET /imagen/{sku}       cómo se ve

── Contra qué corre ───────────────────────────────────────────────────────────

`SAP_BASE_URL` apunta hoy a `tools-agente-catusita`, que es el servicio real
—no el Mock SAP—. El mock sigue desplegado en Railway pero ya no lo consulta
nadie: quedó de la etapa anterior.

Por eso NO hay default en el código. Si falta la variable, esto revienta al
arrancar en vez de pegarle en silencio a un servidor con datos de prueba y
contestarle a un asesor un stock que no existe.

── Por qué su propio cliente y no uno compartido ──────────────────────────────

Había un `shared/sap_client.py` con los 12 endpoints, y todas las áreas lo
importaban. Eso significaba que `productos` podía llamar a `/vendedor/{id}/clientes`
sin que nada lo impidiera: el método estaba ahí, a un punto de distancia.

Acá no está. `productos` no tiene forma de consultar una cartera porque no
existe el método en su backend. No es una regla que haya que recordar — es que
el código no está.

── El precio ──────────────────────────────────────────────────────────────────

`tipo` sale como parámetro y NO tiene default. Para vendedores puede ser "neto"
o "lista"; para clientes solo "lista", y por eso el backend de clientes ni
siquiera acepta el argumento. Un default acá sería la forma más fácil de que un
precio neto se escape por el canal equivocado.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

# Sin default a propósito: ver la nota del encabezado.
BASE_URL = os.getenv("SAP_BASE_URL", "")
API_KEY = os.getenv("SAP_API_KEY", "")

# Las imágenes se descargan enteras; el resto son consultas de datos.
TIMEOUT = 10.0
TIMEOUT_IMAGEN = 30.0

_cliente: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _cliente
    if _cliente is None:
        if not BASE_URL:
            raise RuntimeError(
                "Falta SAP_BASE_URL. Hoy apunta a tools-agente-catusita; el Mock "
                "SAP quedó de la etapa anterior y ya no se usa."
            )
        _cliente = httpx.AsyncClient(
            base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=TIMEOUT
        )
    return _cliente


async def _get(path: str, params: dict | None = None, timeout: float | None = None) -> dict:
    """GET con errores en castellano y sin excepciones hacia arriba.

    Devuelve `{"error": ...}` en vez de lanzar: una caída de SAP tiene que
    llegar al orquestador como un dato que puede explicarle al asesor, no como
    una excepción que le tumba el turno.
    """
    try:
        kwargs: dict = {"params": params}
        if timeout is not None:
            kwargs["timeout"] = timeout
        r = await _http().get(path, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"No encontrado: {path}"}
        return {"error": f"Error del servidor SAP: {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "La consulta tardó demasiado. Inténtalo de nuevo en un momento."}
    except httpx.RequestError:
        return {"error": "No se pudo conectar al servidor SAP. Inténtalo en unos minutos."}


async def stock(sku: str) -> dict:
    return await _get(f"/stock/{sku}")


async def precios(sku: str, tipo: str) -> dict:
    """`tipo` es obligatorio: "neto" o "lista". Ver la nota del encabezado."""
    return await _get(f"/precios/{sku}", params={"tipo": tipo})


async def catalogo(q: str | None = None, categoria: str | None = None,
                   marca: str | None = None, con_stock: bool | None = None) -> dict:
    params: dict = {}
    if q:
        params["q"] = q
    if categoria:
        params["categoria"] = categoria
    if marca:
        params["marca"] = marca
    if con_stock is not None:
        params["con_stock"] = str(con_stock).lower()
    return await _get("/catalogo", params=params or None)


async def imagen(sku: str) -> dict:
    """Foto(s) del producto, ya descargadas en base64."""
    return await _get(f"/imagen/{sku}", timeout=TIMEOUT_IMAGEN)


async def cerrar() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.aclose()
        _cliente = None
