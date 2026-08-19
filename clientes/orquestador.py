"""Orquestador de Clientes. Único que le habla al usuario y único que coordina.

Le habla a: Talleres, distribuidores y consumidor final.
Alcance:    Solo información pública: stock, precio de lista, catálogo y reclamos.

Ve 5 áreas, no la lista de tools internas:

      productos        ¿Tienen esta pieza y cuánto cuesta?
      vehiculos        ¿Qué auto es y qué le sirve?
      postventa        Quiero reclamar o devolver algo.
      recomendaciones  ¿Qué más me puede servir?
      conocimiento     ¿Cómo se hace esto? (fallback: lo que no cae en ninguna)

RAZONA, no solo enruta. Las áreas traen datos; él saca conclusiones
cruzándolos. «¿Este filtro le entra a mi Corolla 2015?» no es una consulta a
ningún lado: `vehiculos` dice qué auto es, `productos` dice qué hay en catálogo,
y él cruza las dos cosas. Por eso no existe un área de compatibilidad.

── El RAG de procesos no es un extra ──────────────────────────────────────────

TODO proceso que este orquestador ejecute está documentado en
`conocimiento_clientes`: cómo se resuelve (`pasos`) y cómo se entrega la
respuesta (`entrega`). No solo los casos raros — todos. Lo que no está en la
tabla, no lo sabe hacer.

`contexto` se los deja servidos en CADA turno, antes de que este nodo corra. No
los va a buscar cuando se traba: ya los tiene.

    en el prompt     quién es, cómo habla, qué no puede revelar.
                     Lo transversal, lo que no cambia entre consultas.

    en el RAG        cómo se tramita una garantía, qué se responde ante un
                     reclamo, cómo se explica un envío a provincia — y cómo se
                     redacta la respuesta de cada uno.

El criterio: si algo se puede corregir sin redeployar, va en el RAG.

Y una frontera propia de este multiagente: acá NUNCA sale precio neto, cartera
ni condición de crédito. Eso vive en `conocimiento_vendedores`, que es otra
tabla — no un WHERE que se pueda olvidar.

TODO: migrar la parte transversal desde orchestrator/prompts.py — y al hacerlo,
separar qué de ese prompt es transversal y qué son procesos que deben salir a
`conocimiento_clientes` como filas.
"""

SYSTEM = """TODO: prompt del orquestador de clientes."""


async def nodo_orquestador(state) -> dict:
    raise NotImplementedError
