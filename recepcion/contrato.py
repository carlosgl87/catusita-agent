"""El contrato entre el webhook y los agentes. Lo único que cruza un proceso.

Hay UNA sola frontera de proceso en todo el sistema:

    webhook ──Turno──► cola "vendedores" ──► worker vendedores
                                                  │
                                          orquestador ⇄ áreas
                                          (todo en el mismo proceso)
                                                  │
    WAHA ◄──Respuesta── cola "respuestas:vendedores" ◄┘

Adentro del worker no hay contrato que respetar: el orquestador invoca a las
áreas con `Command(goto=...)` y comparten el `EstadoAgente` en memoria.

── Lo que este archivo tenía antes, y por qué se fue ──────────────────────────

Había un tercer sobre, `Encargo`, para que el orquestador le pidiera algo a un
área por Redis: delegaba, guardaba un checkpoint, se liberaba, y reanudaba
cuando el resultado volvía a su cola.

Eso es ejecución durable, y era un error para este sistema. Convertía cada
delegación en un viaje por Redis y obligaba a checkpointing solo para no
bloquear un worker — cuando en asyncio el orquestador no bloquea nada mientras
espera. Se pagaba complejidad para romper `Command(goto=...)`, que es
justamente el mecanismo con el que el orquestador coordina.

Quedan dos sobres, y los dos cruzan la única frontera real.

── Por qué versión ────────────────────────────────────────────────────────────

El webhook y los workers son servicios distintos y se despliegan por su cuenta.
Un día el webhook encola con un campo nuevo y el worker todavía corre la imagen
anterior. `version` deja que el consumidor lo detecte y falle claro, en vez de
romperse de formas raras tres pasos después.
"""
from dataclasses import dataclass, asdict, field
from typing import Any
import json
import time
import uuid

VERSION = 3


def _id() -> str:
    return uuid.uuid4().hex


@dataclass
class Turno:
    """Lo que el webhook le manda al worker: un turno del usuario ya unido.

    Sale del acumulador, así que `texto` puede ser la unión de varios fragmentos
    que llegaron seguidos y `media` la de varias imágenes.

    ── `perfil` viaja vacío ───────────────────────────────────────────────────

    La recepción decide a QUÉ multiagente va el mensaje —con el padrón de
    Redis— pero no sabe qué es un `vendedor_id`: no lee ninguna tabla. Quién es
    este número lo resuelve cada worker contra su propio roster.

    El campo queda igual porque es donde el worker lo escribe al armar el
    estado, y porque el día que la recepción tenga algo que aportar (un alias,
    el nombre que muestra WhatsApp) entra por acá sin cambiar el sobre.

    ── `lock` ─────────────────────────────────────────────────────────────────

    El token del lock de conversación, que la recepción tomó ANTES de reclamar
    los fragmentos. Viaja hasta el Resultado y vuelve, y recién ahí se suelta:
    la conversación queda tomada mientras el worker trabaja, así un segundo
    mensaje no arranca una corrida encima de la primera.
    """
    conversacion: str            # el número, normalizado
    multiagente: str             # "vendedores" | "clientes" | "supervisores"
    texto: str
    perfil: dict
    media: list = field(default_factory=list)
    responder_a: str = ""        # from_field de WAHA (puede ser un @lid)
    lock: str = ""               # token del lock de conversación
    id: str = field(default_factory=_id)
    ts: float = field(default_factory=time.time)
    version: int = VERSION


@dataclass
class Resultado:
    """Lo que el worker devuelve cuando terminó el turno.

    Es la respuesta al usuario, no un dato intermedio: el grafo ya corrió
    entero, pasó por `validar` y esto es lo que se envía por WhatsApp.

    `ok=False` con `error` también se devuelve, a propósito. El usuario merece
    un «no pude»; el silencio es peor que un error.

    `lock` vuelve tal cual vino en el Turno. El worker no lo mira: solo lo
    devuelve para que la recepción libere la conversación cuando la respuesta
    ya esté en el chat.
    """
    conversacion: str
    multiagente: str
    ok: bool
    texto: str = ""              # la respuesta redactada
    media: list = field(default_factory=list)
    responder_a: str = ""
    lock: str = ""               # el que vino en el Turno, sin tocar
    tools: list = field(default_factory=list)   # para la telemetría del panel
    error: str = ""
    duracion_ms: int = 0
    id: str = field(default_factory=_id)
    ts: float = field(default_factory=time.time)
    version: int = VERSION


# ── Serialización ─────────────────────────────────────────────────────────────

_TIPOS = {"Turno": Turno, "Resultado": Resultado}


def empacar(obj) -> str:
    """Sobre -> JSON para la cola. El tipo viaja adentro."""
    d = asdict(obj)
    d["_tipo"] = type(obj).__name__
    return json.dumps(d, ensure_ascii=False)


def desempacar(raw: str):
    """JSON de la cola -> sobre. Falla claro si la versión no coincide.

    Un `VersionIncompatible` en los logs dice exactamente qué pasó: hay dos
    servicios desplegados en versiones distintas. Sin esto, el síntoma sería un
    KeyError en algún punto raro y perderías una hora buscándolo.
    """
    d = json.loads(raw)
    tipo = _TIPOS.get(d.pop("_tipo", ""))
    if tipo is None:
        raise ValueError(f"sobre desconocido en la cola: {raw[:120]}")
    v = d.get("version")
    if v != VERSION:
        raise VersionIncompatible(
            f"{tipo.__name__} v{v} pero este servicio corre v{VERSION}. "
            f"Hay servicios desplegados en commits distintos."
        )
    return tipo(**d)


class VersionIncompatible(RuntimeError):
    """Dos servicios en versiones distintas del contrato."""
