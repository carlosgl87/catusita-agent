"""El contrato entre servicios. La pieza central de la arquitectura distribuida.

Cada agente es un servicio con su propia cola. Como ya no comparten proceso, lo
único que los une es la forma de estos dos sobres. Si esto cambia, cambia en
todos lados a la vez.

── El ciclo ───────────────────────────────────────────────────────────────────

    webhook ──Turno──► v:supervisor
                          │
                          │ decide, guarda checkpoint, SE LIBERA
                          ▼
                       v:productos ──► [servicio productos] ──Resultado──┐
                                                                          │
                       v:supervisor ◄──────────────────────────────────────┘
                          │
                          │ reanuda desde el checkpoint, redacta
                          ▼
                       enviar por WAHA

El supervisor NUNCA bloquea esperando. Delega y termina su turno. Cuando el
resultado vuelve a su cola, se reanuda desde donde quedó. Por eso hace falta
`checkpoint_id`: es lo que permite que el proceso que reanuda no sea el mismo
que delegó — ni siquiera la misma instancia.

── Por qué versión ────────────────────────────────────────────────────────────

Con servicios separados, cada uno se despliega por su cuenta. Un día el
supervisor encola con un campo nuevo y el servicio de productos todavía corre la
imagen anterior. `version` deja que el consumidor lo detecte y falle claro, en
vez de romperse de formas raras tres pasos después.
"""
from dataclasses import dataclass, asdict, field
from typing import Any
import json
import time
import uuid

VERSION = 1


def _id() -> str:
    return uuid.uuid4().hex


@dataclass
class Turno:
    """Lo que el webhook le manda al supervisor: un turno del usuario ya unido.

    Va a la cola `{p}:supervisor`. Sale del acumulador, así que `texto` puede ser
    la unión de varios fragmentos y `media` la de varias imágenes.
    """
    conversacion: str            # el número, normalizado
    multiagente: str                # "vendedores" | "clientes"
    texto: str
    perfil: dict                 # lo resolvió el router; el worker no re-autentica
    media: list = field(default_factory=list)
    responder_a: str = ""        # from_field de WAHA (puede ser un @lid)
    id: str = field(default_factory=_id)
    ts: float = field(default_factory=time.time)
    version: int = VERSION


@dataclass
class Encargo:
    """Lo que el supervisor le pide a un agente de área.

    Va a la cola propia del área (`v:productos`, `c:postventa`…).

    `checkpoint_id` es lo importante: identifica el estado del grafo del
    supervisor que quedó guardado al delegar. El agente no lo interpreta — lo
    devuelve tal cual para que el supervisor sepa dónde reanudar.
    """
    conversacion: str
    multiagente: str
    area: str                    # a quién va dirigido
    consulta: str                # qué se le pide, en lenguaje natural
    contexto: dict               # entidades ya resueltas (RUC, SKU, placa…)
    checkpoint_id: str           # dónde reanudar al volver
    perfil: dict
    id: str = field(default_factory=_id)
    ts: float = field(default_factory=time.time)
    version: int = VERSION


@dataclass
class Resultado:
    """Lo que un agente le devuelve al supervisor. Va a `{p}:supervisor`.

    `falta` es la salida cuando el agente no puede terminar solo: no llama a
    nadie, dice qué necesita y el supervisor decide a quién preguntarle. Es la
    regla de "las áreas no se hablan entre sí", ahora expresada en el contrato
    en vez de en el grafo.
    """
    conversacion: str
    multiagente: str
    area: str                    # quién responde
    checkpoint_id: str           # el que venía en el Encargo
    ok: bool
    datos: Any = None            # lo que encontró
    media: list = field(default_factory=list)
    falta: str = ""              # "necesito el N° de documento de este RUC"
    error: str = ""
    duracion_ms: int = 0
    id: str = field(default_factory=_id)
    ts: float = field(default_factory=time.time)
    version: int = VERSION


# ── Serialización ─────────────────────────────────────────────────────────────

_TIPOS = {"Turno": Turno, "Encargo": Encargo, "Resultado": Resultado}


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
