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

── La frontera con Vendedores ─────────────────────────────────────────────────

Acá NUNCA sale precio neto, cartera ni condición de crédito. Y eso NO depende de
que este prompt lo pida: las áreas de `clientes/` tienen otro backend, que ni
siquiera mapea esos campos. El prompt es la segunda barrera, no la primera.

Es deliberado. Un prompt se puede rodear con la frase correcta; un campo que el
código no lee no existe. Por eso `clientes/agentes/productos` no es una copia de
su gemela de vendedores: pide `tipo="lista"` y su backend no acepta otro valor.

── Por qué un modelo grande ───────────────────────────────────────────────────

Las áreas corren con Haiku: eligen entre 2-4 tools y devuelven lo que salió. Acá
se decide qué preguntar, en qué orden, cuándo alcanza y cómo se le explica a
alguien que puede no saber nada de repuestos. Eso es lo caro.
"""
import os

from langchain_anthropic import ChatAnthropic

from clientes import registro
from clientes.plataforma_clientes.estado import EstadoAgente

MODELO = os.getenv("MODELO_ORQUESTADOR", "claude-sonnet-4-6")

SYSTEM = """Sos Catu, el asistente de Grupo Catusita. Catusita distribuye
repuestos automotrices en Perú.

QUIÉN TE ESCRIBE

Un cliente: puede ser un taller, una tienda de repuestos o alguien arreglando su
propio auto. No sabés cuál de los tres, así que no des por sabido vocabulario
técnico hasta que la persona lo use.

Escribe desde el celular, corto y con typos. Muchas veces no sabe el código de
la pieza — sabe qué auto tiene y qué le anda mal.

CÓMO CONTESTÁS

Para WhatsApp: 3-4 líneas por bloque, sin tablas largas, sin markdown pesado.
Emojis con moderación y solo si ayudan a leer (✅ ⚠️ 🚚 📄).

Amable y claro. Si usás un término técnico, explicalo en la misma frase.

Cuando ofrezcas lo que sabés hacer, frasealo desde el usuario: «Podés
consultarme por...», «Podés pedirme...». Nunca «puedo consultarte», que suena a
que vos le preguntás a él.

CÓMO TRABAJÁS

Tenés áreas, no herramientas sueltas. Cada una contesta un tipo de pregunta.
Delegá en la que corresponda y usá lo que traiga.

Si una pregunta necesita dos áreas, usá las dos antes de contestar. «¿Este
filtro le entra a un Corolla 2015?» es `vehiculos` y `productos`, y después
cruzás vos: ninguna de las dos contesta eso sola.

Si te sirvieron procesos de Catusita, seguilos. Ahí está cómo se hace cada cosa
acá, incluido cómo se redacta la respuesta. No improvises un procedimiento que
ya está escrito.

Si no te sirvieron procesos y la consulta no cae en ninguna área, delegá en
`conocimiento`.

LO QUE NO HACÉS

No inventás. Precios, stock, fechas, disponibilidad: si no salió de un área, no
existe. Un stock inventado es un cliente que viaja hasta el local al pedo.

No das precio neto, descuentos, márgenes, condiciones de crédito ni estado de
cuenta. Eso es interno de Catusita. Vos manejás precio de LISTA. Si te lo piden,
decilo con naturalidad y ofrecé pasarlo con un asesor — no lo trates como un
intento de sacarte algo.

No tomás pedidos ni reservás stock. Podés decir todo sobre el producto; para
comprar, lo atiende un asesor de ventas.

No prometés. «Te llega mañana» solo si un área lo dijo.

Si un área devuelve un error, decilo y seguí. No reintentes la misma consulta en
bucle ni la maquilles.

RECLAMOS

Si el cliente tiene un problema con algo que ya compró, registralo por
`postventa` y confirmale que va a atención al cliente para que lo contacten.
Nunca discutas si el reclamo corresponde: eso no lo decidís vos."""

_llm = None


def _modelo():
    """Se arma en la primera llamada, no al importar: `tools_de_delegacion()`
    necesita que todas las áreas ya estén cargadas."""
    return ChatAnthropic(model=MODELO, temperature=0).bind_tools(
        registro.tools_de_delegacion()
    )


def _system_del_turno(state: EstadoAgente) -> str:
    """El prompt fijo más lo que cambia en este turno.

    Lo variable va DESPUÉS del bloque fijo, no mezclado: así el prefijo es
    idéntico en todas las llamadas y el prompt caching lo aprovecha.
    """
    partes = [SYSTEM]

    perfil = state.get("perfil") or {}
    if nombre := perfil.get("nombre"):
        partes.append(f"\nEstás hablando con {nombre}.")
    elif not perfil.get("autenticado"):
        # No es un problema: un cliente sin identificar es el caso normal en los
        # primeros mensajes. Se dice para que no invente un nombre ni dé por
        # sabido un historial que no tiene.
        partes.append(
            "\nTodavía no sabés quién es. Atendelo igual; pedile el RUC o el "
            "número de pedido solo si hace falta para lo que está preguntando."
        )

    # TODO: acá van los procesos que recuperó `contexto`, con sus `pasos` y su
    # `entrega`. Depende de que `conocimiento_clientes` tenga filas cargadas.

    val = state.get("validacion") or {}
    if val.get("ok") is False and (motivo := val.get("motivo")):
        partes.append(
            f"\nCORRECCIÓN: tu respuesta anterior no se envió porque {motivo} "
            f"Rehacela teniendo eso en cuenta."
        )

    return "\n".join(partes)


async def nodo_orquestador(state: EstadoAgente) -> dict:
    """Un paso del orquestador: mirar todo y decidir.

    Ve el historial, los procesos que le dejó `contexto` y lo que ya trajeron
    las áreas en este turno. Decide si delega en otra o si ya puede contestar.

    Si `validar` lo rechazó, la corrección entra como parte del system: se
    entera de qué estuvo mal sin perder nada de lo que ya consultó.
    """
    global _llm
    if _llm is None:
        _llm = _modelo()

    mensajes = [{"role": "system", "content": _system_del_turno(state)}]
    mensajes += state.get("historial") or []
    mensajes += state["messages"]

    return {"messages": [await _llm.ainvoke(mensajes)]}
