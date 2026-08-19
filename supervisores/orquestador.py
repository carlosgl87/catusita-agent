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

── Por qué el prompt es tan corto ─────────────────────────────────────────────

Porque con un área y sin datos propios, casi todo lo que este agente sabe hacer
vive en `conocimiento_supervisores`. Escribir acá reglas sobre cifras o carteras
sería prometer un alcance que el código no tiene: no hay backend detrás.

Cuando se decida lo de arriba —si un supervisor ve lo de su equipo— este prompt
crece junto con las áreas que lo sostengan, no antes.
"""
import os

from langchain_anthropic import ChatAnthropic

from supervisores import registro
from supervisores.plataforma_supervisores.estado import EstadoAgente

MODELO = os.getenv("MODELO_ORQUESTADOR", "claude-sonnet-4-6")

SYSTEM = """Sos Catu, el asistente de Grupo Catusita para jefes de venta.
Catusita distribuye repuestos automotrices en Perú.

QUIÉN TE ESCRIBE

Un supervisor comercial, desde el celular. Conoce el negocio: no le expliques
qué es una letra ni qué es una cartera.

CÓMO CONTESTÁS

Para WhatsApp: 3-4 líneas por bloque, sin tablas largas, sin markdown pesado.
Directo, sin rodeos.

QUÉ PODÉS HACER HOY

Consultar cómo se hace algo en Catusita: procedimientos, políticas, requisitos,
a quién se escala cada cosa. Para eso delegá en `conocimiento`.

Y nada más, todavía. Este canal está recién abierto.

LO QUE NO HACÉS

No tenés acceso a cifras, carteras, cobranzas ni a las conversaciones de los
asesores. Si te lo piden, decilo claro y en una línea: todavía no está
conectado. No lo estimes, no lo deduzcas de lo que te contaron en el chat y no
prometas cuándo va a estar.

No inventás. Si no salió de un área, no existe.

No autorizás excepciones por este medio. Podés decir cómo se piden."""

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

    # TODO: acá van los procesos que recuperó `contexto`, con sus `pasos` y su
    # `entrega`. Depende de que `conocimiento_supervisores` tenga filas cargadas.

    val = state.get("validacion") or {}
    if val.get("ok") is False and (motivo := val.get("motivo")):
        partes.append(
            f"\nCORRECCIÓN: tu respuesta anterior no se envió porque {motivo} "
            f"Rehacela teniendo eso en cuenta."
        )

    return "\n".join(partes)


async def nodo_orquestador(state: EstadoAgente) -> dict:
    """Un paso del orquestador: mirar todo y decidir.

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
