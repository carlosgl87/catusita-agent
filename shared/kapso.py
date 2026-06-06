"""
Cliente para Kapso (WhatsApp Cloud API oficial vía Meta).

Reemplaza a shared/evolution.py manteniendo una interfaz compatible
(send_message / send_document) para que el resto del código no cambie.

Docs: https://docs.kapso.ai
Endpoint base: https://api.kapso.ai/meta/whatsapp/v24.0/{phone_number_id}/messages
"""
import os
import hmac
import hashlib

import httpx
from dotenv import load_dotenv

load_dotenv()

KAPSO_BASE_URL = os.getenv(
    "KAPSO_BASE_URL", "https://api.kapso.ai/meta/whatsapp/v24.0"
).rstrip("/")
KAPSO_API_KEY = os.getenv("KAPSO_API_KEY", "")
KAPSO_PHONE_NUMBER_ID = os.getenv("KAPSO_PHONE_NUMBER_ID", "")
KAPSO_WEBHOOK_SECRET = os.getenv("KAPSO_WEBHOOK_SECRET", "")


# ---------------------------------------------------------------------------
# Verificación de firma del webhook (HMAC-SHA256 del body crudo)
# ---------------------------------------------------------------------------
def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verifica que `X-Webhook-Signature` coincida con HMAC-SHA256(secret, body).

    Si no está configurado el secret, deja pasar (modo dev) pero loguea aviso.
    """
    if not KAPSO_WEBHOOK_SECRET:
        print("[KAPSO] AVISO: KAPSO_WEBHOOK_SECRET no configurado; firma no se valida")
        return True

    if not signature_header:
        return False

    expected = hmac.new(
        KAPSO_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header.strip())


def _normalizar_numero(numero: str) -> str:
    """
    Quita prefijos (+), sufijos (@s.whatsapp.net) y agrega 51 si falta.
    """
    n = (numero or "").lstrip("+").split("@")[0]
    if n and not n.startswith("51"):
        n = "51" + n
    return n


# ---------------------------------------------------------------------------
# Cliente para enviar mensajes
# ---------------------------------------------------------------------------
class KapsoClient:
    def __init__(self):
        self._headers = {
            "X-API-Key": KAPSO_API_KEY,
            "Content-Type": "application/json",
        }

    def _send_url(self, phone_number_id: str | None = None) -> str:
        pnid = phone_number_id or KAPSO_PHONE_NUMBER_ID
        return f"{KAPSO_BASE_URL}/{pnid}/messages"

    async def send_message(self, numero: str, instance: str, texto: str) -> dict:
        """
        Envía un mensaje de texto.

        Args:
            numero: destinatario (con o sin 51 al inicio, con o sin @s.whatsapp.net).
            instance: ignorado (compat con la interfaz de EvolutionClient).
            texto: contenido a enviar.
        """
        numero_clean = _normalizar_numero(numero)
        body = {
            "messaging_product": "whatsapp",
            "to": numero_clean,
            "type": "text",
            "text": {"body": texto},
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self._send_url(), headers=self._headers, json=body)
            if resp.status_code >= 400:
                # Loguear cuerpo del error antes de raise_for_status
                print(f"[KAPSO] error {resp.status_code}: {resp.text}")
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
        """Envía un documento (PDF, XML, etc) por URL pública."""
        numero_clean = _normalizar_numero(numero)
        doc_payload: dict = {"link": url, "filename": filename}
        if caption:
            doc_payload["caption"] = caption
        body = {
            "messaging_product": "whatsapp",
            "to": numero_clean,
            "type": "document",
            "document": doc_payload,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self._send_url(), headers=self._headers, json=body)
            if resp.status_code >= 400:
                print(f"[KAPSO] error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()


kapso = KapsoClient()
