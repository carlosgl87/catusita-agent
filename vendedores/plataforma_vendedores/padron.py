"""Padrón de vendedores: le dice al router qué números son míos.

Al arrancar, este multiagente lee SU roster (`vendedores`) y vuelca los números a
Redis. Eso es todo.

    vendedores  ──(al prender)──►  Redis  hash "padron"  {numero: "vendedores"}
                                            ▲
                                            │ HGET, una lectura por mensaje
                                        la recepción

── Por qué solo Redis y no una tabla ──────────────────────────────────────────

El padrón no es un dato, es un ÍNDICE DERIVADO del roster. Se reconstruye entero
en un segundo, así que no necesita historia, ni reconciliación, ni sobrevivir a
un reinicio de Redis: si Redis se cae, los agentes lo repueblan al arrancar.

Hubo una versión con cuatro tablas (una por multiagente más una consolidada para
el dashboard, con fechas de alta y detección de choques). Resolvía problemas que
solo existen si el padrón es persistente. No lo es.

La fuente de verdad sigue siendo `vendedores`, que no se toca acá.

── Republica cada tanto ───────────────────────────────────────────────────────

Si solo publicara al arrancar, dar de alta a alguien no tendría efecto hasta el
próximo deploy: entraría al multiagente equivocado sin que nadie entienda por qué.
"""
import logging

from vendedores.plataforma_vendedores import db
from vendedores.plataforma_vendedores import redis as redis_mod

MULTIAGENTE = "vendedores"
ROSTER = "vendedores"
CLAVE = "padron"

CADA_SEGUNDOS = 300


async def publicar() -> int:
    """Vuelca mi roster a Redis. Devuelve cuántos números publicó.

    Escribe SOLO sus propias entradas del hash: `HSET padron <numero> "vendedores"`.
    Los de otros multiagentes viven en el mismo hash y no se tocan.
    """
    pool = await db.get()
    async with pool.acquire() as c:
        filas = await c.fetch(
            """SELECT whatsapp FROM vendedores
                WHERE activo AND whatsapp IS NOT NULL AND whatsapp <> ''"""
        )
    numeros = [f["whatsapp"] for f in filas]
    if not numeros:
        logging.warning(f"[padron] {ROSTER} no tiene números con whatsapp cargado")
        return 0

    r = await redis_mod.get()
    await r.hset(CLAVE, mapping={n: MULTIAGENTE for n in numeros})

    # Soltar los que ya no están en el roster. Solo míos: se recorre el hash y
    # se borran las entradas que dicen ser de este multiagente y ya no lo son.
    actuales = set(numeros)
    sobrantes = [
        n for n, dueno in (await r.hgetall(CLAVE)).items()
        if dueno == MULTIAGENTE and n not in actuales
    ]
    if sobrantes:
        await r.hdel(CLAVE, *sobrantes)

    logging.info(f"[padron] {MULTIAGENTE}: {len(numeros)} números, {len(sobrantes)} dados de baja")
    return len(numeros)
