"""Orquestador de Vendedores. Único que le habla al usuario y único que coordina.

Le habla a: Asesores comerciales internos de Catusita.
Alcance:    Acceso completo: precio neto, cartera, pedidos, documentos y cobranza.

Ve 6 áreas, no la lista de tools internas:

      productos        ¿Qué pieza es, existe, cuánto vale y cómo se ve?
      vehiculos        ¿Qué auto es esta placa?
      clientes         ¿Quién es este cliente y está en mi cartera?
      pedidos          ¿Dónde está el pedido y ya llegó?
      facturacion      ¿Está pagada? Mándame el PDF.
      conocimiento     ¿Cómo se hace esto? (fallback: lo que no cae en ninguna)

RAZONA, no solo enruta. Las áreas traen datos; él saca conclusiones
cruzándolos. «¿Este filtro le entra a mi Corolla 2015?» no es una consulta a
ningún lado: `vehiculos` dice qué auto es, `productos` dice qué hay en catálogo,
y él cruza las dos cosas. Por eso no existe un área de compatibilidad.

Para razonar usa lo que le deja `contexto`: la conversación en curso, lo que
sabemos de quien escribe, y el RAG de procesos.

── El RAG de procesos no es un extra ──────────────────────────────────────────

TODO proceso que este orquestador ejecute está documentado en `conocimiento`:
cómo se resuelve (`pasos`) y cómo se entrega la respuesta (`entrega`). No solo
los casos raros — todos. Lo que no está en la tabla, no lo sabe hacer.

`contexto` se los deja servidos en CADA turno, antes de que este nodo corra. No
los va a buscar cuando se traba: ya los tiene.

Eso fija qué va en el prompt y qué no:

    en el prompt     quién es, cómo habla, qué no puede revelar.
                     Lo transversal, lo que no cambia entre consultas.

    en el RAG        cómo se atiende un despacho demorado, qué se hace si
                     SUNARP se cae, cuándo se deriva a créditos, cómo se
                     redacta la respuesta de cada uno de esos casos.

El criterio: si algo se puede corregir sin redeployar, va en el RAG. Y hoy casi
todo lo que nos piden corregir es de ese tipo.

Ojo que esto cambia lo que decía antes: los procedimientos NO viven en el prompt
del área. El área sabe consultar su backend; el procedimiento de negocio es del
orquestador y se recupera.

TODO: migrar la parte transversal desde orchestrator/prompts.py — y al hacerlo,
separar qué de ese prompt es transversal y qué son procesos que deben salir a
`conocimiento` como filas.
"""

SYSTEM = """TODO: prompt del orquestador de vendedores."""


async def nodo_orquestador(state) -> dict:
    raise NotImplementedError
