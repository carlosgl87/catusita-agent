"""Entrypoint de los contenedores de agentes.

    python -m clientes.plataforma_clientes.worker

Levanta turnos de UNA cola —la de su multiagente— y corre el grafo entero.

── Qué hace y qué no ──────────────────────────────────────────────────────────

NO despacha por área. El worker no sabe qué es `productos` ni `facturacion`: le
entrega el turno al grafo y el ORQUESTADOR decide a qué áreas va, con
`Command(goto=...)`, todo dentro de este mismo proceso.

Esa es la división:

    el worker         transporte. Saca de Redis, corre, devuelve.
    el orquestador    coordinación. A qué área, en qué orden, cuándo cortar.

Una versión anterior tenía una cola por área y el worker despachaba a cada una.
Era un error: convertía cada delegación en un viaje por Redis y obligaba a
ejecución durable con checkpoints, perdiendo justamente el `Command(goto=...)`
en proceso con el que el orquestador coordina. Ver plataforma/colas.py.

── Los tres contenedores ──────────────────────────────────────────────────────

    catusita-agent          uvicorn main:app     webhook + router (encola)
    catusita-vendedores     worker vendedores    grafo de vendedores
    catusita-clientes       worker clientes      grafo de clientes
    catusita-supervisores   worker supervisores  grafo de supervisores

Un proceso por multiagente atiende todas sus conversaciones. En asyncio eso no
las serializa: un `await` de 60 s contra SUNARP no bloquea el event loop.
"""
import asyncio
import importlib
import logging
import time

from clientes.plataforma_clientes import colas
from clientes.plataforma_clientes import padron
from clientes.plataforma_clientes import redis as redis_mod
from clientes.plataforma_clientes.contrato import (
    Resultado, VersionIncompatible, desempacar, empacar,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# El BRPOP se despierta cada tanto para poder atender un apagado. No es polling.
BLOQUEO = 5


def cargar_grafo():
    """El grafo compilado del multiagente.

    Se importa acá y no arriba para que el worker de vendedores no cargue el
    módulo de clientes ni por accidente de import.
    """
    mod = importlib.import_module("clientes.grafo")
    grafo = getattr(mod, "grafo", None)
    if grafo is None:
        raise RuntimeError(
            "clientes/grafo.py no expone `grafo` compilado. "
            f"Falta descomentar `grafo = construir().compile()`."
        )
    fallos = mod.verificar_topologia(grafo)
    if fallos:
        for f in fallos:
            logging.error(f"[topología] {f}")
        raise RuntimeError(f"grafo de clientes mal armado: {len(fallos)} violación(es)")
    return grafo


async def correr() -> None:
    # Antes de escuchar nada: que el mapa de colas cierre. Una cola sin
    # consumidor acumula turnos en silencio, que es la peor forma de fallar.
    fallos = colas.problemas()
    if fallos:
        for f in fallos:
            logging.error(f"[colas] {f}")
        raise RuntimeError(f"mapa de colas inconsistente: {len(fallos)} problema(s)")

    cola = colas.COLA
    grafo = cargar_grafo()
    registro = importlib.import_module("clientes.registro")

    areas = registro.mapa()
    logging.info(f"worker de clientes · cola={cola} · {len(areas)} áreas en el grafo")
    for nombre, (modelo, tools) in sorted(areas.items()):
        logging.info(f"    {nombre:16} {modelo:28} {len(tools)} tools")

    # El padrón, antes de escuchar: si no publico, el router no sabe que estos
    # números son míos y sus dueños entran al multiagente equivocado.
    await padron.publicar()
    asyncio.create_task(_republicar())

    r = await redis_mod.get()
    while True:
        item = await r.brpop([cola], timeout=BLOQUEO)
        if item is None:
            continue
        _, crudo = item

        try:
            turno = desempacar(crudo)
        except VersionIncompatible as e:
            # Reintentar no arregla un desajuste de versiones entre despliegues.
            logging.error(f"contrato incompatible: {e}")
            await r.rpush(f"muertos:{cola}", crudo)
            continue
        except Exception as e:
            logging.error(f"sobre ilegible: {e}")
            await r.rpush(f"muertos:{cola}", crudo)
            continue

        t0 = time.time()
        try:
            res = await _correr_turno(grafo, turno)
        except Exception as e:
            logging.exception(f"turno {turno.conversacion} falló: {e}")
            # El error vuelve igual. El usuario merece un "no pude"; el silencio
            # es peor que un error.
            res = Resultado(
                conversacion=turno.conversacion, multiagente="clientes",
                ok=False, error=str(e),
            )
        res.duracion_ms = int((time.time() - t0) * 1000)
        await r.lpush(colas.COLA_RESPUESTAS, empacar(res))
        logging.info(f"turno {turno.conversacion} en {res.duracion_ms} ms ok={res.ok}")


async def _republicar() -> None:
    """Republica el padrón cada tanto. Sin esto, un alta no tendría efecto hasta
    el próximo deploy: el número entraría al multiagente equivocado sin que nadie
    entienda por qué."""
    while True:
        await asyncio.sleep(padron.CADA_SEGUNDOS)
        try:
            await padron.publicar()
        except Exception as e:
            logging.error(f"[padron] republicación falló: {e}")


async def _correr_turno(grafo, turno) -> Resultado:
    """Corre el grafo completo para un turno.

    TODO: invocar `grafo.ainvoke()` con el EstadoAgente armado desde el turno
    (conversacion, perfil, messages) y sacar de la salida la respuesta y la
    media pendiente. Depende de que los subgrafos de las áreas estén compilados.
    """
    raise NotImplementedError


def main() -> None:
    asyncio.run(correr())


if __name__ == "__main__":
    main()
