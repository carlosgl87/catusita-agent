"""Acceso de `productos` (clientes) a las BACKEND APIS.

Cuatro endpoints y ninguno más:

    GET /stock/{sku}        cuánto hay
    GET /precios/{sku}      cuánto vale
    GET /catalogo?q=        qué existe
    GET /imagen/{sku}       cómo se ve

Es un archivo distinto del de `vendedores` aunque peguen al MISMO endpoint. Esa
duplicación es el punto, no un descuido: acá vive la frontera.

── La frontera es una ALLOWLIST, no una regla ─────────────────────────────────

Cada respuesta se recorta a los campos permitidos, uno por uno. No se filtra
«lo prohibido»: se copia «lo permitido».

La diferencia importa. Con una blocklist, el día que el endpoint agregue
`precio_neto` o `almacen`, el campo pasa derecho al modelo y de ahí al chat de
un cliente — sin que nadie cambie una línea ni salte un test. Con allowlist, un
campo nuevo simplemente no existe de este lado hasta que alguien decida
agregarlo a mano.

Hoy `/stock` ni siquiera devuelve almacén y `/precios` devuelve lo mismo para
`tipo=neto` y `tipo=lista`. Es decir: la protección todavía no protege de nada
real. Por eso hay que escribirla AHORA — cuando el endpoint cambie, nadie se va
a acordar de que este canal existía.

── El precio ──────────────────────────────────────────────────────────────────

`precios()` no acepta el argumento `tipo` y manda `lista` fijo. En vendedores es
un parámetro obligatorio sin default; acá directamente no está. Un default sería
la forma más fácil de que un precio neto se escape por el canal equivocado; no
tener el argumento es que no haya forma de pedirlo.
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

# Sin default a propósito: mejor reventar al arrancar que pegarle en silencio a
# un servidor de prueba y contestarle a un cliente un stock que no existe.
BASE_URL = os.getenv("SAP_BASE_URL", "")
API_KEY = os.getenv("SAP_API_KEY", "")

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

    Devuelve `{"error": ...}` en vez de lanzar: una caída del backend tiene que
    llegar al orquestador como un dato que puede explicarle al cliente, no como
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
        return {"error": f"Error del servidor: {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "La consulta tardó demasiado. Inténtalo de nuevo en un momento."}
    except httpx.RequestError:
        return {"error": "No se pudo conectar al servidor. Inténtalo en unos minutos."}


def _recortar(datos: dict, permitidos: tuple) -> dict:
    """Deja SOLO los campos de `permitidos`. Los errores pasan enteros.

    Un `{"error": ...}` no se recorta porque no trae datos del negocio y porque
    el orquestador necesita el texto completo para poder explicarlo.
    """
    if not isinstance(datos, dict) or datos.get("error"):
        return datos
    return {k: datos[k] for k in permitidos if k in datos}


# Campos que este canal puede ver. Agregar uno acá es una decisión explícita.
_STOCK = ("sku", "nombre", "marca", "unidad", "disponible")
_PRECIO = ("sku", "precio_lista", "moneda")
_PRODUCTO = ("sku", "nombre", "categoria", "marca")


async def stock(sku: str) -> dict:
    """Si hay o no. NO devuelve la cantidad exacta ni el almacén.

    La cantidad se omite a propósito: a un cliente le sirve saber si puede pasar
    a buscarlo, y el número exacto es información de inventario que además
    envejece mal — se la damos y a la hora ya no es cierta.
    """
    return _recortar(await _get(f"/stock/{sku}"), _STOCK)


async def precios(sku: str) -> dict:
    """Precio de LISTA. Sin argumento `tipo`: ver la nota del encabezado."""
    return _recortar(await _get(f"/precios/{sku}", params={"tipo": "lista"}), _PRECIO)


async def catalogo(q: str | None = None, categoria: str | None = None,
                   marca: str | None = None) -> dict:
    params: dict = {}
    if q:
        params["q"] = q
    if categoria:
        params["categoria"] = categoria
    if marca:
        params["marca"] = marca

    datos = await _get("/catalogo", params=params or None)
    if not isinstance(datos, dict) or datos.get("error"):
        return datos
    return {
        "productos": [_recortar(p, _PRODUCTO) for p in (datos.get("productos") or [])]
    }


async def imagen(sku: str) -> dict:
    """Foto(s) del producto, ya descargadas en base64."""
    return await _get(f"/imagen/{sku}", timeout=TIMEOUT_IMAGEN)


async def cerrar() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.aclose()
        _cliente = None
