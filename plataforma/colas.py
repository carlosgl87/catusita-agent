"""Mapa de colas. Sale de lo que declara cada agente, no de una lista central.

Cada área declara su `COLA` en su `__init__.py`. Hoy varias comparten la misma,
y eso es a propósito: el número de colas debe seguir al número de **perfiles de
runtime**, no al de agentes.

    ┌─ el agente declara ─┐        ┌─ el operador levanta ─┐
      COLA = "rapida"        →        1 worker  rapida
      COLA = "lenta"         →        1 worker  lenta

Para darle cola propia a un agente: cambias su `COLA` y levantas un worker que
la consuma. Ni el grafo ni el supervisor se enteran. Así el diseño llega a
"una cola por agente" el día que haga falta, sin pagarlo hoy.

── Por qué hoy son dos y no once ──────────────────────────────────────────────

Una cola por agente obliga a decidir qué hace el supervisor mientras espera:
bloquearse (dos workers ocupados por un turno, sin ganar paralelismo) o
liberarse y reanudar desde un checkpoint (ejecución durable, bastante más
máquina). En los dos casos se pierde `Command(goto=...)` en proceso.

Con el volumen medido —~22.000 comandos de Redis en 82 días, pico de 1,64 MB,
unas 35-50 conversaciones diarias— ese costo no se paga solo.

Lo que SÍ justifica una cola aparte es el perfil de runtime: SUNARP tarda 20-60s
y se cuelga. Sin separarlo, una consulta de stock espera detrás de él.
"""
import importlib
import logging
import pkgutil
from collections import defaultdict
from pathlib import Path

MULTIAGENTES = ("vendedores", "clientes")

# Nombre de la cola -> qué worker la consume. Solo documentación operativa: el
# reparto real lo declara cada agente.
WORKERS = {
    "rapida": "catusita-worker",
    "lenta": "catusita-worker-lento",
}


def _areas():
    for prod in MULTIAGENTES:
        d = Path(__file__).parent.parent / prod / "agentes"
        if not d.is_dir():
            continue
        for info in pkgutil.iter_modules([str(d)]):
            if not info.ispkg:
                continue
            try:
                mod = importlib.import_module(f"{prod}.agentes.{info.name}")
            except Exception as e:
                logging.error(f"[colas] {prod}/{info.name} no importa: {e}")
                continue
            yield prod, info.name, mod


def mapa() -> dict:
    """{cola: [(multiagente, area), ...]}. Lo que cada worker debe atender."""
    m = defaultdict(list)
    for prod, nombre, mod in _areas():
        m[getattr(mod, "COLA", "rapida")].append((prod, nombre))
    return dict(m)


def cola_de(multiagente: str, area: str) -> str:
    """En qué cola se procesa una delegación a esta área."""
    for prod, nombre, mod in _areas():
        if prod == multiagente and nombre == area:
            return getattr(mod, "COLA", "rapida")
    return "rapida"


def colas() -> list:
    """Colas que hay que consumir. Si alguien declara una nueva, aparece acá y
    el arranque puede avisar que le falta worker."""
    return sorted(mapa())


def sin_worker() -> list:
    """Colas declaradas por algún agente para las que nadie levantó worker.

    Correrlo al arrancar: una cola sin consumidor acumula jobs en silencio, que
    es la peor forma de fallar — parece que anda hasta que alguien reclama.
    """
    return [c for c in colas() if c not in WORKERS]
