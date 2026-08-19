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

VERSION = 2


def _id() -> str:
    return uuid.uuid4().hex


@dataclass
class Turno:
    """Lo que el webhook le manda al worker: un turno del usuario ya unido.

    Sale del acumulador, así que `texto` puede ser la unión de varios fragmentos
    que llegaron seguidos y `media` la de varias imágenes.

    `perfil` viaja resuelto: lo hizo el router al decidir a qué cola va. El
    worker NO re-autentica — si lo hiciera, un cambio en `auth` podría mandar el
    turno a un multiagente y autenticarlo como el otro.
    """
    conversacion: str            # el número, normalizado
    multiagente: str             # "vendedores" | "clientes" | "supervisores"
    texto: str
    perfil: dict
    media: list = field(default_factory=list)
    responder_a: str = ""        # from_field de WAHA (puede ser un @lid)
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
    """
    conversacion: str
    multiagente: str
    ok: bool
    texto: str = ""              # la respuesta redactada
    media: list = field(default_factory=list)
    responder_a: str = ""
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
