"""Cliente de WAHA. Lo único del sistema que le habla a WhatsApp.

    https://waha.devlike.pro/docs/    imagen devlikeapro/waha (Core)

Ningún worker importa este módulo. Un área que manda una foto la deja en
`media_pendiente` y sigue; el worker la pone en el Resultado; recepción la
envía. Por eso el día que WhatsApp se cambie por otro canal, cambia este archivo
y nada más.

── La sesión va como parámetro ────────────────────────────────────────────────

Una sesión de WAHA es un número conectado. La versión anterior la leía de una
global (`WAHA_SESSION`) y la metía sola en cada request, así que todo salía por
el mismo número aunque hubiera tres.

Acá la decide quien llama —`numeros.sesion_de(multiagente)`—, que con un solo
número devuelve ese y con tres devuelve el que corresponde. Mismo código para
los dos casos.

── Los errores no se lanzan ───────────────────────────────────────────────────

`enviar_*` devuelve bool. Un turno puede traer un texto y tres fotos: si la
segunda foto falla, las otras dos tienen que salir igual. Con excepciones, un
403 en un archivo se llevaría puesta la respuesta completa.
"""
import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("WAHA_BASE_URL", "http://localhost:3000").rstrip("/")
API_KEY = os.getenv("WAHA_API_KEY", "")

TIMEOUT_TEXTO = 15.0
TIMEOUT_ARCHIVO = 30.0

PREFIJO = "51"


def headers() -> dict:
    return {"X-Api-Key": API_KEY, "Content-Type": "application/json"}


def url_de(ruta: str) -> str:
    """WAHA devuelve las URLs de media como rutas relativas ('/api/files/...').
    Pegarle el host acá evita que cada quien se acuerde de hacerlo."""
    if ruta.startswith(("http://", "https://")):
        return ruta
    return f"{BASE_URL}/{ruta.lstrip('/')}"


def chat_id(numero: str) -> str:
    """Número -> chatId de WAHA.

    Si ya trae '@' se devuelve tal cual: puede ser '...@c.us' o '...@lid', y un
    LID hay que responderlo como LID.
    """
    if "@" in numero:
        return numero
    n = numero.lstrip("+")
    if not n.startswith(PREFIJO):
        n = PREFIJO + n
    return f"{n}@c.us"


async def resolve_lid_to_phone(lid: str, session: str) -> str | None:
    """LID de Meta -> teléfono. None si WAHA no lo sabe.

    WhatsApp entrega para muchos contactos el identificador interno de Meta en
    vez del número. Sin traducirlo, el HGET contra el padrón no matchea y el
    asesor entra como cliente.

        GET /api/{session}/lids/{lid}  ->  {"lid": "...@lid", "pn": "51...@c.us"}
    """
    lid_id = lid if lid.endswith("@lid") else f"{lid}@lid"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{BASE_URL}/api/{session}/lids/{lid_id}", headers=headers())
            if r.status_code != 200:
                logging.warning(f"[waha] lids/{lid_id} -> {r.status_code}")
                return None
            tel = ((r.json() or {}).get("pn") or "").split("@")[0].lstrip("+")
            return tel or None
    except Exception as e:
        logging.warning(f"[waha] no se pudo resolver el LID {lid_id}: {e}")
        return None


async def _post(ruta: str, body: dict, timeout: float) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{BASE_URL}/api/{ruta}", headers=headers(), json=body)
            if r.status_code >= 400:
                logging.error(f"[waha] {ruta} -> {r.status_code}: {r.text[:200]}")
                return False
            return True
    except Exception as e:
        logging.error(f"[waha] {ruta} falló: {e}")
        return False


async def enviar_texto(session: str, destino: str, texto: str) -> bool:
    if not texto:
        return False
    return await _post(
        "sendText",
        {"session": session, "chatId": chat_id(destino), "text": texto},
        TIMEOUT_TEXTO,
    )


def _crudo(b64: str) -> str:
    """WAHA Core hace atob() sobre el campo, así que el data URI lo rompe."""
    return b64.split(",", 1)[1] if b64.startswith("data:") else b64


def _mime_de(filename: str) -> str:
    f = filename.lower()
    if f.endswith(".png"):
        return "image/png"
    if f.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


async def enviar_media(session: str, destino: str, item: dict) -> bool:
    """Manda UN adjunto de los que dejaron las áreas en `media_pendiente`.

    Las áreas producen dos formas, y la clave dice cuál es:

        {"imagen_base64", "caption", "filename"}            fotos de producto
        {"documento_base64", "caption", "filename", "mime"} PDFs de facturación

    Distinguir por clave y no por un campo "tipo" es a propósito: el área no
    tiene que acordarse de rotularlo, y una forma que no se reconoce se loguea
    en vez de mandarse mal.
    """
    cid = chat_id(destino)
    caption = item.get("caption", "")

    if img := item.get("imagen_base64"):
        nombre = item.get("filename") or "imagen.jpg"
        return await _post("sendImage", {
            "session": session, "chatId": cid, "caption": caption,
            "file": {"mimetype": _mime_de(nombre), "filename": nombre,
                     "data": _crudo(img)},
        }, TIMEOUT_ARCHIVO)

    if doc := item.get("documento_base64"):
        nombre = item.get("filename") or "documento.pdf"
        return await _post("sendFile", {
            "session": session, "chatId": cid, "caption": caption,
            "file": {"mimetype": item.get("mime") or "application/pdf",
                     "filename": nombre, "data": _crudo(doc)},
        }, TIMEOUT_ARCHIVO)

    logging.error(f"[waha] adjunto sin forma conocida: {sorted(item)}")
    return False
