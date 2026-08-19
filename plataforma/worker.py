"""Entrypoint de los contenedores de agentes.

    python -m plataforma.worker vendedores

Recibe el MULTIAGENTE, no una cola. Al arrancar recorre sus agentes, les lee la
`COLA` que cada uno declara y consume todas a la vez.

Eso importa: el nombre de la cola se declara UNA sola vez, en el
`__init__.py` del agente. Ni el Dockerfile ni el arranque lo repiten. Si un
agente cambia su cola, este worker la sigue sin que nadie toque nada más.

Sin eso, el modo de fallar sería el peor posible: el supervisor encolando en un
nombre y el worker escuchando otro, sin un solo error, con los jobs apilándose
en una cola que nadie lee.

── Los tres contenedores ──────────────────────────────────────────────────────

    catusita-supervisor    uvicorn main:app          webhook + router + supervisores
    catusita-vendedores    worker vendedores         las 6 áreas de vendedores
    catusita-clientes      worker clientes           las 5 áreas de clientes

Un solo proceso por multiagente atiende todas sus áreas. En asyncio eso NO las
serializa: un `await` de 60 segundos contra SUNARP no bloquea el event loop, así
que las otras áreas siguen respondiendo mientras tanto.

Si algún día un agente necesita aislarse de verdad, se levanta otro contenedor
con la misma imagen filtrando por su cola. El código no cambia.
"""
import asyncio
import importlib
import logging
import pkgutil
import sys
import time
from pathlib import Path

from plataforma import redis as redis_mod
from plataforma.contrato import (
    Encargo, Resultado, VersionIncompatible, desempacar, empacar,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# El BRPOP se despierta cada tanto para poder atender un apagado. No es polling.
BLOQUEO = 5


def agentes_de(multiagente: str) -> dict:
    """{cola: (nombre, modulo)} leyendo el contrato de cada agente del multiagente."""
    d = Path(__file__).parent.parent / multiagente / "agentes"
    encontrados = {}
    for info in pkgutil.iter_modules([str(d)]):
        if not info.ispkg:
            continue
        mod = importlib.import_module(f"{multiagente}.agentes.{info.name}")
        cola = getattr(mod, "COLA", None)
        if not cola:
            # Falla al arrancar, no en silencio a las tres de la mañana.
            raise RuntimeError(
                f"{multiagente}/agentes/{info.name} no declara COLA en su __init__.py"
            )
        if cola in encontrados:
            raise RuntimeError(
                f"cola {cola!r} declarada por {info.name} y por {encontrados[cola][0]}"
            )
        encontrados[cola] = (info.name, mod)
    return encontrados


async def _ejecutar(multiagente: str, area: str, mod, encargo: Encargo) -> Resultado:
    """Corre el subgrafo del agente y arma su Resultado.

    TODO: invocar mod.NODO con la consulta y el contexto del encargo.
    """
    raise NotImplementedError


async def correr(multiagente: str) -> None:
    agentes = agentes_de(multiagente)
    colas = list(agentes)
    cola_supervisor = f"{multiagente}:supervisor"

    logging.info(f"worker de {multiagente} · {len(agentes)} agentes")
    for cola, (nombre, mod) in sorted(agentes.items()):
        logging.info(f"    {nombre:16} cola={cola:22} modelo={mod.MODELO}")

    r = await redis_mod.get()
    while True:
        # BRPOP con varias claves: devuelve de la primera que tenga algo.
        item = await r.brpop(colas, timeout=BLOQUEO)
        if item is None:
            continue
        cola, raw = item
        nombre, mod = agentes[cola]

        try:
            encargo = desempacar(raw)
        except VersionIncompatible as e:
            # Reintentar no arregla un desajuste de versiones entre despliegues.
            logging.error(f"[{nombre}] contrato incompatible: {e}")
            await r.rpush(f"muertos:{cola}", raw)
            continue
        except Exception as e:
            logging.error(f"[{nombre}] sobre ilegible: {e}")
            await r.rpush(f"muertos:{cola}", raw)
            continue

        t0 = time.time()
        try:
            res = await _ejecutar(multiagente, nombre, mod, encargo)
        except Exception as e:
            logging.exception(f"[{nombre}] falló: {e}")
            # El error vuelve al supervisor. El usuario merece un "no pude";
            # el silencio es peor que un error.
            res = Resultado(
                conversacion=encargo.conversacion, multiagente=multiagente, area=nombre,
                checkpoint_id=encargo.checkpoint_id, ok=False, error=str(e),
            )
        res.duracion_ms = int((time.time() - t0) * 1000)
        await r.lpush(cola_supervisor, empacar(res))
        logging.info(f"[{nombre}] resuelto en {res.duracion_ms} ms ok={res.ok}")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python -m plataforma.worker <vendedores|clientes>")
    asyncio.run(correr(sys.argv[1]))


if __name__ == "__main__":
    main()
