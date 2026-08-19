"""Tools de `productos` (vendedores). El orquestador NO ve estas cuatro.

El orquestador delega en el ÁREA («averiguá qué pieza es, si hay y cuánto
vale») y es el subgrafo de acá el que decide cuáles de estas usar y en qué
orden. Por eso las descripciones están escritas para el modelo del área, no
para el del orquestador: pueden ser más técnicas y dar por sabido el contexto.

Las cuatro devuelven `Command` en vez de un string: así el resultado entra al
estado como ToolMessage y, en el caso de las imágenes, además deja la foto en
`media_pendiente` para que el worker la mande por WhatsApp.
"""
import json
from typing import Annotated, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from vendedores.agentes.productos import backend, servicio


def _responder(resultado: dict, tool_call_id: str, extra: dict | None = None) -> Command:
    """Empaqueta el resultado como ToolMessage y lo aplica al estado."""
    update: dict = {
        "messages": [
            ToolMessage(
                content=json.dumps(resultado, ensure_ascii=False, default=str),
                tool_call_id=tool_call_id,
            )
        ]
    }
    if extra:
        update.update(extra)
    return Command(update=update)


@tool
async def consultar_stock(
    sku_code: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Stock disponible de un producto por SKU, con el desglose por almacén.
    Usar cuando pregunten por disponibilidad, inventario o si hay un producto."""
    resultado = await backend.stock(sku_code)
    return _responder(await servicio.con_sugerencias(sku_code, resultado), tool_call_id)


@tool
async def consultar_precio(
    sku_code: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Precio NETO de un producto por SKU: el que el asesor cotiza, ya con su
    descuento. Es información interna — quien la recibe decide qué comparte."""
    resultado = await backend.precios(sku_code, tipo="neto")
    return _responder(await servicio.con_sugerencias(sku_code, resultado), tool_call_id)


@tool
async def buscar_catalogo(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    categoria: Optional[str] = None,
    marca: Optional[str] = None,
) -> Command:
    """Busca productos por nombre, categoría o marca cuando NO se tiene el SKU.
    Usar para encontrar repuestos por descripción o ver qué equivalentes hay.

    Si ya tenés el SKU exacto, usá consultar_stock o consultar_precio: son
    directas y esta es una búsqueda."""
    resultado = await backend.catalogo(q=query, categoria=categoria, marca=marca)
    return _responder(resultado, tool_call_id)


@tool
async def enviar_imagen_producto(
    sku_code: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Manda la(s) FOTO(s) de un producto al chat de WhatsApp. Usar solo cuando
    pidan la imagen o la foto de un producto puntual por su SKU.

    La foto se envía sola: en el texto solo hay que confirmar que se mandó, sin
    describirla ni pedir que la busquen."""
    resultado = await backend.imagen(sku_code)

    if not resultado or resultado.get("error"):
        return _responder(
            {
                "error": "SIN_IMAGEN",
                "mensaje": f"No hay foto del producto {sku_code} en el sistema.",
            },
            tool_call_id,
        )

    media = servicio.a_media(sku_code, resultado)
    if not media:
        return _responder(
            {"error": "SIN_IMAGEN", "mensaje": f"No hay foto del producto {sku_code}."},
            tool_call_id,
        )

    # `media_pendiente` tiene reducer de suma en EstadoAgente: si en un mismo
    # turno se piden fotos de dos productos, se acumulan y salen las dos.
    return _responder(
        {
            "sku": sku_code,
            "nombre": resultado.get("nombre", ""),
            "enviadas": len(media),
            "mensaje": f"Se enviaron {len(media)} foto(s) del producto {sku_code}.",
        },
        tool_call_id,
        {"media_pendiente": media},
    )


TOOLS = [
    consultar_stock,
    consultar_precio,
    buscar_catalogo,
    enviar_imagen_producto,
]
