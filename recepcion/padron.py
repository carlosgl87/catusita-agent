"""El padrón, del lado que LEE.

Cada multiagente publica en Redis qué números son suyos, sacándolos de su
roster. Acá solo se consulta:

    HGET padron 51987654321  ->  "vendedores"

Una lectura por mensaje. La recepción no toca Postgres y no conoce ninguna
tabla: no sabe qué es un `vendedor_id` ni un RUC.

── Qué pasa si el número no está ──────────────────────────────────────────────

Cae a `clientes`, que es el multiagente que menos ve. Nunca al revés.

Eso cubre solos varios casos que si no habría que tratar uno por uno: número
nuevo, agente que todavía no arrancó, Redis recién reiniciado, LID que no se
pudo traducir. Todos terminan en el lado seguro sin código extra.

── Qué pasa si Redis no responde ──────────────────────────────────────────────

También `clientes`. Un asesor atendido como cliente es una molestia; un
desconocido atendido como asesor es una fuga de cartera.
"""
import logging

from recepcion import redis as redis_mod

CLAVE = "padron"

# Adónde va todo lo que no se pudo resolver.
POR_DEFECTO = "clientes"


async def multiagente_de(numero: str) -> tuple[str, str]:
    """(multiagente, motivo). El motivo se loguea: es la auditoría del ruteo.

    Devolver el motivo y no solo el destino es lo que hace depurable un ruteo
    equivocado. Sin él, «entró como cliente» no dice si fue porque no estaba en
    el padrón, porque Redis falló, o porque efectivamente es un cliente.
    """
    if not numero:
        return POR_DEFECTO, "sin número"

    try:
        r = await redis_mod.get()
        dueno = await r.hget(CLAVE, numero)
    except Exception as e:
        logging.error(f"[padron] Redis no respondió: {e}")
        return POR_DEFECTO, "padrón inaccesible"

    if not dueno:
        return POR_DEFECTO, "no está en el padrón"

    return dueno, f"padrón dice {dueno}"


async def tamano() -> dict:
    """Cuántos números publicó cada multiagente. Para /health y para diagnosticar.

    Un multiagente en cero es un contenedor que no arrancó o que no logró
    publicar — y sus usuarios están entrando como clientes ahora mismo.
    """
    try:
        r = await redis_mod.get()
        todos = await r.hgetall(CLAVE)
    except Exception:
        return {}
    conteo: dict = {}
    for dueno in todos.values():
        conteo[dueno] = conteo.get(dueno, 0) + 1
    return conteo
