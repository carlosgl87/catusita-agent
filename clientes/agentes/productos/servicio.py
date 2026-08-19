"""Lógica de `productos` (clientes). Lo que el backend no hace solo.

El backend trae datos crudos. Acá se decide qué hacer cuando esos datos no
alcanzan — que en esta área es casi siempre el mismo caso: **el SKU no existe**.

── Por qué el fallback de SKU importa MÁS acá que en vendedores ───────────────

Un asesor escribe el código de memoria y se equivoca. Un cliente muchas veces
NO TIENE el código: copia lo que dice la caja vieja, o lo que le pasó el
mecánico por WhatsApp, o un número que leyó de la pieza gastada.

Sin fallback, la respuesta es «no encontré ese producto» y la conversación se
corta ahí. Con fallback, el mismo error devuelve las coincidencias del catálogo
y el orquestador puede preguntar «¿te referís a alguno de estos?».

MAX_SUGERENCIAS = 5 porque van a un mensaje de WhatsApp: más que eso no se lee.
"""
from clientes.agentes.productos import backend

MAX_SUGERENCIAS = 5


def _no_encontrado(resultado: dict) -> bool:
    return bool(
        resultado.get("error")
        or resultado.get("detail") == "Producto no encontrado"
    )


async def con_sugerencias(sku: str, resultado: dict) -> dict:
    """Si el SKU no existe, busca parecidos en el catálogo y los propone.

    Si la búsqueda de respaldo también falla, devuelve el error original: es
    peor confundir al cliente con un segundo error que dejarle el primero claro.
    """
    if not _no_encontrado(resultado):
        return resultado

    try:
        encontrados = await backend.catalogo(q=sku)
        productos = encontrados.get("productos", []) if isinstance(encontrados, dict) else []
    except Exception:
        return resultado

    if not productos:
        return resultado

    return {
        "error": "PRODUCTO_NO_ENCONTRADO_SUGERENCIAS",
        "mensaje": (
            f"No existe ningún producto con el código exacto '{sku}'. "
            "Estas son las coincidencias del catálogo: preguntale al usuario si "
            "se refiere a alguna."
        ),
        # Ya vienen recortadas por el backend: sku, nombre, categoria, marca.
        "sugerencias": productos[:MAX_SUGERENCIAS],
    }


def a_media(sku: str, resultado: dict) -> list[dict]:
    """Convierte la respuesta de `/imagen` en lo que WhatsApp necesita.

    El caption va SOLO en la primera: repetirlo en cada foto de un mismo
    producto llena el chat de texto igual.
    """
    nombre = resultado.get("nombre", "")
    return [
        {
            "imagen_base64": img["base64"],
            "caption": f"{nombre} — {sku}" if i == 0 else "",
            "filename": img.get("filename", f"{sku}.png"),
        }
        for i, img in enumerate(resultado.get("imagenes", []))
    ]
