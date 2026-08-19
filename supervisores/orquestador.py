"""Orquestador de Supervisores. Único que le habla al usuario y único que coordina.

Le habla a: Jefes de venta de Catusita.
Alcance:    SIN DEFINIR. Ver abajo.

OJO: este archivo era una copia literal del de vendedores. Listaba 6 áreas que
este multiagente no tiene y describía a la audiencia equivocada.

Ve 1 área:

      conocimiento     ¿Cómo se hace esto en Catusita?

── Lo que falta decidir antes de que esto crezca ──────────────────────────────

¿Un supervisor puede ver la cartera, las cifras y las conversaciones de SUS
asesores? Si la respuesta es sí, este multiagente necesita áreas de datos
propias y una noción de «mi equipo» que hoy no existe en ningún lado — el
control de acceso está pensado para «lo mío», no para «lo de los míos».

Mientras eso no se resuelva, acá solo se consultan procedimientos.

── El RAG de procesos no es un extra ──────────────────────────────────────────

TODO proceso que este orquestador ejecute está documentado en
`conocimiento_supervisores`: cómo se resuelve (`pasos`) y cómo se entrega la
respuesta (`entrega`). No solo los casos raros — todos. Lo que no está en la
tabla, no lo sabe hacer.

`contexto` se los deja servidos en CADA turno, antes de que este nodo corra.

    en el prompt     quién es, cómo habla, qué no puede revelar.
    en el RAG        todo lo demás.

El criterio: si algo se puede corregir sin redeployar, va en el RAG.

TODO: migrar la parte transversal desde orchestrator/prompts.py.
"""

SYSTEM = """TODO: prompt del orquestador de supervisores."""


async def nodo_orquestador(state) -> dict:
    raise NotImplementedError
