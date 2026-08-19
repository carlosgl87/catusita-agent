"""Memoria. Lo que el orquestador sabe antes de que le pregunten.

Corre antes que el orquestador y le deja servido todo lo que no es el mensaje
de ahora. Tres capas, que se agregan en este orden:

    1. MEMORIA CORTO PLAZO   la conversación en curso
       Redis, TTL 2h. Es lo único implementado hoy.
       -> migrar desde orchestrator/context.py::get_history

    2. MEMORIA LARGO PLAZO   qué sabemos de quien escribe
       Qué preguntó antes, qué compra, qué vehículos maneja, qué se le
       prometió. Sobrevive entre conversaciones.
       -> pgvector sobre Postgres

    3. RAG DE PROCESOS       cómo se hace esto en Catusita
       Los procedimientos: cómo se determina si una pieza calza, cuándo se
       deriva a créditos, qué se responde ante un reclamo. Reglas de negocio
       recuperables, no hardcodeadas en un prompt.
       -> pgvector; ver db/migrations/004_conocimiento.sql (sin aplicar:
          falta elegir el proveedor de embeddings)

       ESTA CAPA CORRE EN TODOS LOS TURNOS. No es un plan B para cuando el
       orquestador se traba: es de donde saca cómo trabajar, siempre. Todo
       proceso que ejecute tiene que estar en la tabla — lo que no está, no lo
       sabe hacer. Y cada proceso trae su `entrega`: no solo cómo resolverlo,
       también cómo presentarlo.

── Por qué esto está acá y no en un área ──────────────────────────────────────

Las áreas TRAEN DATOS. El orquestador RAZONA. Esa es la división.

Un ejemplo concreto: «¿este filtro le entra a mi Corolla 2015?» no es una
consulta, es una conclusión. `vehiculos` trae qué auto es, `productos` trae qué
hay en catálogo, y el orquestador cruza las dos cosas siguiendo el
procedimiento que le recupera el RAG. No hay un área de compatibilidad porque
no hay un dato de compatibilidad que buscar.

Por eso este nodo alimenta al orquestador y no a las áreas: es él quien
necesita saber cómo se razona.
"""
import json
import logging

from supervisores.plataforma_supervisores import redis as redis_mod
from supervisores.plataforma_supervisores.estado import EstadoAgente

TTL = 7200        # 2 horas de inactividad
MAX_MENSAJES = 20 # 10 turnos (user + assistant)

# Cuántos procesos se le pasan al orquestador por turno. Bajo a propósito: cada
# uno se paga en tokens en todas las llamadas del turno.
K_PROCESOS = 3

# Debajo de esta similitud se considera que NO hay proceso y se abre ticket.
# Provisional: hay que calibrarlo con documentos reales cargados. Muy alto llena
# la cola de tickets falsos; muy bajo aplica procedimientos que no venían al caso.
UMBRAL = 0.35


async def nodo_contexto(state: EstadoAgente) -> dict:
    """Arma la memoria y la deja en el estado.

    Ya no hace falta pasarle el multiagente: este módulo vive dentro de
    `supervisores/`, así que sus claves y sus tablas son las de supervisores y ninguna otra.

    Hoy arma solo la capa 1. Las otras dos se agregan acá cuando existan.
    """
    return {"historial": await _corto_plazo(state["conversacion"])}


def _clave(conversacion: str) -> str:
    """`conv:supervisores:51999...`

    El multiagente va en la clave, no solo en el valor: aunque el router fallara
    y mandara un número al worker equivocado, no podría leer el historial que ese
    número tiene del otro lado. La clave vieja era `conversation:{numero}`, sin
    esa separación.
    """
    return f"conv:supervisores:{conversacion}"


async def _corto_plazo(conversacion: str) -> list:
    """Historial de la conversación. Redis, TTL 2h.

    Ante un fallo de Redis devuelve [] en vez de romper: perder el contexto de
    los últimos turnos degrada la respuesta, pero dejar sin contestar a un asesor
    es peor. Se loguea para que no pase inadvertido.
    """
    try:
        r = await redis_mod.get()
        crudo = await r.get(_clave(conversacion))
        return json.loads(crudo) if crudo else []
    except Exception as e:
        logging.warning(f"contexto: no se pudo leer el historial ({e})")
        return []


async def guardar(conversacion: str, rol: str, contenido: str) -> None:
    """Agrega un mensaje al historial y renueva el TTL.

    Lo llama el worker al cerrar el turno, no el grafo: el grafo lee memoria, no
    la escribe. Si escribiera, un reintento de validación duplicaría mensajes.
    """
    try:
        r = await redis_mod.get()
        k = _clave(conversacion)
        historial = await _corto_plazo(conversacion)
        historial.append({"role": rol, "content": contenido})
        await r.setex(k, TTL, json.dumps(historial[-MAX_MENSAJES:], ensure_ascii=False))
    except Exception as e:
        logging.warning(f"contexto: no se pudo guardar el mensaje ({e})")


async def olvidar(conversacion: str) -> None:
    """Borra el historial. El comando «reiniciar» del usuario."""
    try:
        r = await redis_mod.get()
        await r.delete(_clave(conversacion))
    except Exception as e:
        logging.warning(f"contexto: no se pudo borrar el historial ({e})")


async def _largo_plazo(conversacion: str, perfil: dict) -> dict:
    """Lo que sabemos de esta persona de conversaciones anteriores.

    Ojo con el alcance: para un vendedor esto incluye su cartera y su
    histórico; para un cliente, solo lo suyo. La memoria hereda las mismas
    fronteras que los datos — recordar no puede ser una vía para revelar.

    TODO: diseñar. Qué se guarda, cuánto vive, y quién puede leerlo.
    """
    raise NotImplementedError


async def _procesos(consulta: str) -> list:
    """Procedimientos de Catusita que aplican a lo que están preguntando.

    Corre SIEMPRE, antes del orquestador. Busca por similitud contra el `cuando`
    de cada proceso —la situación, no el procedimiento— y devuelve los que
    aplican con sus `pasos` y su `entrega`.

    Devuelve el procedimiento, no la respuesta: el orquestador sigue teniendo
    que razonar y decidir. Lo que cambia es que ya no improvisa el cómo.

    Los procesos son POR MULTIAGENTE. Cómo se atiende un reclamo de un cliente y
    cómo se le contesta a un vendedor sobre lo mismo no son el mismo
    procedimiento. Y no hace falta filtrar: cada multiagente tiene su propia
    tabla, así que la frontera es el nombre de la tabla y no un WHERE.

    ── Si no encuentra nada: se abre una solicitud ────────────────────────────

    Un turno sin proceso recuperado deja al orquestador sin guía. No se
    improvisa y no se traga en silencio: se registra en
    `solicitud_proceso_nuevo_<multiagente>` con origen `sin_resultado`, y queda
    pendiente de que alguien escriba el procedimiento.

        consulta sin proceso -> solicitud -> alguien escribe el proceso
                                               -> se cierra apuntando a la fila

    Hay un SEGUNDO camino que no pasa por acá: cuando sí se recuperó un proceso
    pero al orquestador no le sirve, él llama a `solicitar_proceso_nuevo` y la
    solicitud entra con origen `rechazado`. Ver los tools del área.

    Con eso el sistema dice qué le falta. Es lo que hoy se hace a mano en
    `mejoras/incidencias.json`, sin depender de que el asesor lo reporte.

    Tres cosas que no son obvias al implementarlo:

    a) «NO ENCONTRAR NADA» HAY QUE DEFINIRLO. Una búsqueda por coseno SIEMPRE
       devuelve un top-k; lo que no hay es un resultado *bueno*. Por eso existe
       UMBRAL: por debajo de eso se trata como vacío. Y por eso el ticket guarda
       `mejor_sim` — separa «no existe el proceso» de «existe pero no lo
       recupera», que se arreglan distinto (escribir vs. corregir el `cuando`).

    b) SE AGRUPA, NO SE ACUMULA. La misma carencia va a llegar con veinte
       redacciones distintas. Antes de insertar hay que buscar un ticket
       pendiente parecido y sumarle `veces`. Si no, la lista es ilegible en una
       semana y se pierde justo lo valioso: qué proceso es el más pedido.

    c) EL TICKET NO PUEDE DEMORAR LA RESPUESTA. Se abre fuera del camino del
       usuario. Y si falla el insert, se loguea y se sigue — no se le cae la
       conversación a nadie por no poder registrar un ticket.

    Mientras tanto el orquestador igual tiene que contestar algo. Sin proceso,
    lo honesto es decir que no tiene el procedimiento y derivar. Nunca inventarlo:
    esa es exactamente la respuesta que después aparece como queja.

    ── Lo que sigue abierto ───────────────────────────────────────────────────

    CUÁNTOS PROCESOS ENTRAN. Cada uno son tokens en TODAS las llamadas del
    turno. Meter 5 procesos largos reconstruye el problema que esto vino a
    resolver, solo que pagado en recuperación en vez de en prompt. Empezar con
    k=2 o 3 y medir.

    TODO: implementar. Depende de que se elija el proveedor de embeddings.
    """
    raise NotImplementedError
