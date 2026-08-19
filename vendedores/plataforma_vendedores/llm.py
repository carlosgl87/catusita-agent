"""Cliente Anthropic. Uno por proceso.

Esto es el camino DIRECTO a la API: se usa para las llamadas sueltas que no
pasan por el grafo — hoy, leer la tarjeta de propiedad con visión.

El razonamiento del agente NO pasa por acá: eso lo hace `ChatAnthropic` de
LangChain dentro de cada orquestador y de cada área, que es quien sabe de tools
y de estado. Son dos caminos distintos a propósito.

Migrado desde shared/llm.py.
"""
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Configurable para poder cambiarlo sin tocar código. El default es el que venía
# usando el sistema: cambiarlo es una decisión de comportamiento, no de migración.
MODELO = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

_cliente: anthropic.AsyncAnthropic | None = None


def _get() -> anthropic.AsyncAnthropic:
    global _cliente
    if _cliente is None:
        clave = os.getenv("ANTHROPIC_API_KEY")
        if not clave:
            raise RuntimeError("Falta ANTHROPIC_API_KEY.")
        _cliente = anthropic.AsyncAnthropic(api_key=clave)
    return _cliente


async def crear_mensaje(
    system: str,
    messages: list,
    tools: list | None = None,
    max_tokens: int = 1024,
    modelo: str | None = None,
) -> anthropic.types.Message:
    kwargs = {
        "model": modelo or MODELO,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    return await _get().messages.create(**kwargs)


async def texto_de_imagen(
    imagen_base64: str,
    instruccion: str,
    media_type: str = "image/png",
    max_tokens: int = 1024,
) -> str:
    """Lee una imagen con visión y devuelve el texto extraído.

    Existe porque SUNARP entrega marca, modelo, año y VIN únicamente dentro de la
    foto de la tarjeta de identificación vehicular — no hay campo que consultar.
    """
    r = await _get().messages.create(
        model=MODELO,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": imagen_base64,
                    },
                },
                {"type": "text", "text": instruccion},
            ],
        }],
    )
    return "".join(b.text for b in r.content if hasattr(b, "text")).strip()
