import os
import httpx
from dotenv import load_dotenv

load_dotenv()

EVOLUTION_URL = os.getenv("EVOLUTION_API_URL", "")
EVOLUTION_KEY = os.getenv("EVOLUTION_API_KEY", "")


class EvolutionClient:
    def __init__(self):
        self._headers = {"apikey": EVOLUTION_KEY, "Content-Type": "application/json"}

    async def send_message(self, numero: str, instance: str, texto: str) -> dict:
        numero_fmt = f"51{numero}" if not numero.startswith("51") else numero
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{EVOLUTION_URL}/message/sendText/{instance}",
                headers=self._headers,
                json={"number": numero_fmt, "text": texto},
            )
            resp.raise_for_status()
            return resp.json()

    async def send_document(self, numero: str, instance: str,
                             url: str, filename: str, caption: str = "") -> dict:
        numero_fmt = f"51{numero}" if not numero.startswith("51") else numero
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{EVOLUTION_URL}/message/sendMedia/{instance}",
                headers=self._headers,
                json={
                    "number": numero_fmt,
                    "mediatype": "document",
                    "media": url,
                    "fileName": filename,
                    "caption": caption,
                },
            )
            resp.raise_for_status()
            return resp.json()


evolution = EvolutionClient()
