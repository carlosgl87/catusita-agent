import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-20250514"


async def create_message(
    system: str,
    messages: list,
    tools: list = None,
    max_tokens: int = 1024,
) -> anthropic.types.Message:
    kwargs = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    return await _client.messages.create(**kwargs)
