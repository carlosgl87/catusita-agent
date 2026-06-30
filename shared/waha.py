"""
Cliente para WAHA (WhatsApp HTTP API) — versión Core, imagen devlikeapro/waha.

Mantiene la misma interfaz que shared/kapso.py (send_message / send_document /
send_image_base64) para que el webhook pueda cambiar de proveedor con una sola
variable de entorno (WHATSAPP_PROVIDER=waha|kapso).

Docs: https://waha.devlike.pro/docs/
Endpoint base: http://<host>:3000/api
"""
import os
import base64

import httpx
from dotenv import load_dotenv

load_dotenv()

WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://localhost:3000").rstrip("/")
WAHA_API_KEY  = os.getenv("WAHA_API_KEY", "waha-secret-key-2026")
WAHA_SESSION  = os.getenv("WAHA_SESSION", "default")


def _headers() -> dict:
    return {"X-Api-Key": WAHA_API_KEY, "Content-Type": "application/json"}


def _chat_id(numero: str) -> str:
    """
    Convierte un número a chatId válido para WAHA.
    Si ya tiene @ (ej. '51940351180@c.us' o '111621938671767@lid') lo devuelve tal cual.
    Si es solo dígitos, agrega @c.us (y el prefijo 51 si falta).
    """
    if "@" in numero:
        return numero
    n = numero.lstrip("+")
    if not n.startswith("51"):
        n = "51" + n
    return f"{n}@c.us"


class WAHAClient:
    async def send_message(self, numero: str, instance: str, texto: str) -> dict:
        """
        Envía un mensaje de texto.
        `instance` se ignora (compat con la interfaz de KapsoClient).
        """
        body = {
            "session": WAHA_SESSION,
            "chatId": _chat_id(numero),
            "text": texto,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{WAHA_BASE_URL}/api/sendText",
                headers=_headers(),
                json=body,
            )
            if resp.status_code >= 400:
                print(f"[WAHA] error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()

    async def send_document(
        self,
        numero: str,
        instance: str,
        url: str,
        filename: str,
        caption: str = "",
    ) -> dict:
        """Envía un archivo por URL pública."""
        body = {
            "session": WAHA_SESSION,
            "chatId": _chat_id(numero),
            "file": {"url": url, "filename": filename},
            "caption": caption,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{WAHA_BASE_URL}/api/sendFile",
                headers=_headers(),
                json=body,
            )
            if resp.status_code >= 400:
                print(f"[WAHA] error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()

    async def send_image_base64(
        self,
        numero: str,
        instance: str,
        imagen_base64: str,
        caption: str = "",
        filename: str = "imagen.png",
    ) -> dict:
        """
        Envía una imagen en base64.
        WAHA Core acepta data URI en el campo `file.data`.
        """
        # Detectar tipo real desde el filename si no se especificó
        if filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg"):
            mime = "image/jpeg"
        elif filename.lower().endswith(".png"):
            mime = "image/png"
        else:
            mime = "image/jpeg"
        data_uri = f"data:{mime};base64,{imagen_base64}"
        body = {
            "session": WAHA_SESSION,
            "chatId": _chat_id(numero),
            "file": {"mimetype": mime, "filename": filename, "data": data_uri},
            "caption": caption,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{WAHA_BASE_URL}/api/sendImage",
                headers=_headers(),
                json=body,
            )
            if resp.status_code >= 400:
                print(f"[WAHA] error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()


waha = WAHAClient()
