"""Tools nativas de LangChain para el agente Catusita.

Cada @tool:
  - Solo expone al modelo los parámetros de negocio (sku_code, cliente_ruc, etc.).
  - Recibe `perfil` y `tool_call_id` via InjectedState / InjectedToolCallId (invisible al modelo).
  - Aplica control de acceso por cartera (access.py) para tools RUC-scoped.
  - Retorna Command(update={...}) para actualizar el estado del grafo.

Listas exportadas:
  - TOOLS_VENDEDOR_LC  (12 tools, acceso completo)
  - TOOLS_CLIENTE_LC   (8 tools, solo información pública)
"""
import os
import json
import time
import logging
from typing import Annotated, Optional

from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from agents import (
    stock, prices, orders, credit, documents,
    catalog_rag, vehicle, collections, claims, cartera,
)
from orchestrator import access
from shared import llm
from db import models


_INSTRUCCION_TARJETA_VEHICULAR = (
    "Esta es la foto de una Tarjeta de Identificación Vehicular de SUNARP (Perú). "
    "Extrae y devuelve EN TEXTO, como lista clave: valor, todos los datos legibles del "
    "vehículo: placa, marca, modelo, año de fabricación, color, número de serie/VIN, "
    "número de motor, categoría o clase, combustible y propietario(s) si aparecen. "
    "Usa exactamente los valores que ves, no inventes. Si un campo no se lee, omítelo. "
    "No agregues comentarios ni explicaciones: solo los datos."
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _to_command(resultado: dict, tool_call_id: str, extra: dict | None = None) -> Command:
    """Empaqueta el resultado como ToolMessage y lo aplica al estado via Command."""
    content = json.dumps(resultado, ensure_ascii=False, default=str)
    update: dict = {"messages": [ToolMessage(content=content, tool_call_id=tool_call_id)]}
    if extra:
        update.update(extra)
    return Command(update=update)


_USE_AUTH_MOCK = os.getenv("USE_AUTH_MOCK", "true").lower() == "true"


async def _log(perfil: dict, name: str, t0: float) -> None:
    # En modo mock no hay fila en `conversations`; loguear rompería la FK.
    if _USE_AUTH_MOCK:
        return
    try:
        ms = int((time.time() - t0) * 1000)
        await models.log_tool_usage(
            perfil.get("conversation_id", "mock"),
            perfil.get("vendedor_id", "V001"),
            name, ms,
        )
    except Exception as e:
        logging.error(f"Error log_tool_usage: {e}")


async def _sku_fallback(sku_code: str, resultado: dict) -> dict:
    """Si el SKU no se encontró, busca coincidencias en el catálogo y las sugiere."""
    if not (resultado.get("error") or resultado.get("detail") == "Producto no encontrado"):
        return resultado
    try:
        from shared.sap_client import sap
        search = await sap.get_catalogo(q=sku_code)
        productos = search.get("productos", []) if isinstance(search, dict) else []
    except Exception:
        return resultado
    if not productos:
        return resultado
    return {
        "error": "PRODUCTO_NO_ENCONTRADO_SUGERENCIAS",
        "mensaje": (
            f"No se encontró ningún producto con el SKU exacto '{sku_code}'. "
            "Sin embargo, encontramos estas coincidencias en el catálogo. "
            "Pregúntale al usuario si se refiere a alguna de estas opciones y muéstrale los SKUs:"
        ),
        "sugerencias": [
            {
                "sku": p["sku"],
                "nombre": p["nombre"],
                "categoria": p.get("categoria"),
                "marca": p.get("marca"),
            }
            for p in productos[:5]
        ],
    }


# ─── Stock / precios ──────────────────────────────────────────────────────────

@tool
async def consultar_stock(
    sku_code: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Consulta el stock disponible de un producto en los almacenes. Usar cuando pregunten por disponibilidad, inventario o si hay stock de un producto."""
    perfil = state["perfil"]
    t0 = time.time()
    resultado = await stock.consultar_stock(sku_code)
    resultado = await _sku_fallback(sku_code, resultado)
    await _log(perfil, "consultar_stock", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_precio(
    sku_code: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Consulta el precio de lista de un producto. El agente SOLO muestra precio de lista, nunca precios netos ni descuentos."""
    perfil = state["perfil"]
    t0 = time.time()
    resultado = await prices.consultar_precio(sku_code, tipo="lista")
    resultado = await _sku_fallback(sku_code, resultado)
    await _log(perfil, "consultar_precio", t0)
    return _to_command(resultado, tool_call_id)


# ─── Pedidos / crédito / documentos ──────────────────────────────────────────

@tool
async def buscar_pedido_por_id(
    pedido_id: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Busca el estado, fechas, factura y guía de un pedido conociendo solo su número (ej. PED-000001). Úsala cuando el asesor mencione un número de pedido pero no el RUC del cliente. Devuelve el estado del pedido, número de factura, guía y el cliente_ruc."""
    perfil = state["perfil"]
    t0 = time.time()
    resultado = await orders.consultar_pedido_por_id(pedido_id)
    if not resultado or resultado.get("error"):
        resultado = {"error": "PEDIDO_NO_ENCONTRADO", "pedido_id": pedido_id,
                     "mensaje": f"No se encontró ningún pedido con ID {pedido_id!r}."}
    await _log(perfil, "buscar_pedido_por_id", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_pedidos(
    cliente_ruc: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    estado: Optional[str] = None,
) -> Command:
    """Consulta los pedidos de un cliente por su RUC. Devuelve estado del pedido, número de factura SUNAT, estado de despacho (entregado/rechazado) y notas de crédito. Úsala cuando el asesor pregunte por los pedidos, facturas o despachos de un cliente de su cartera. La búsqueda es por cliente (RUC), no por número de pedido."""
    perfil = state["perfil"]
    args = {"cliente_ruc": cliente_ruc}
    denegado = await access.verificar_acceso_cartera("consultar_pedidos", args, perfil)
    t0 = time.time()
    resultado = denegado or await orders.consultar_pedidos(args["cliente_ruc"], estado)
    await _log(perfil, "consultar_pedidos", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_despacho(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    pedido_id: Optional[str] = None,
    factura: Optional[str] = None,
) -> Command:
    """Consulta el estado de ENTREGA/DESPACHO de un pedido: si ya se entregó, la guía de remisión y las fechas de despacho y entrega. Úsala cuando pregunten '¿ya llegó el pedido?', '¿se entregó?', '¿en qué va el despacho?'. Requiere el N° de pedido o el N° de factura (NO funciona por RUC): si el asesor pregunta por el despacho de un cliente, primero usa consultar_pedidos para obtener sus N° de pedido y luego consulta el despacho de cada uno. Trae un campo 'mensaje' ya redactado que puedes reenviar tal cual."""
    perfil = state["perfil"]
    if not pedido_id and not factura:
        return _to_command(
            {"error": "FALTA_DATO", "mensaje": "Necesito el número de pedido o el número de factura para consultar el despacho."},
            tool_call_id,
        )
    t0 = time.time()
    resultado = await orders.consultar_despacho(pedido_id=pedido_id, factura=factura)
    await _log(perfil, "consultar_despacho", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_credito(
    cliente_ruc: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Consulta el límite de crédito, saldo usado y saldo disponible de un cliente. Solo para asesores comerciales."""
    perfil = state["perfil"]
    args = {"cliente_ruc": cliente_ruc}
    denegado = await access.verificar_acceso_cartera("consultar_credito", args, perfil)
    t0 = time.time()
    resultado = denegado or await credit.consultar_credito(args["cliente_ruc"])
    await _log(perfil, "consultar_credito", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_cobranzas(
    cliente_ruc: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    estado: Optional[str] = None,
) -> Command:
    """Consulta las letras, facturas vencidas y deuda pendiente de un cliente. Usar para revisar estado de cobranza."""
    perfil = state["perfil"]
    args = {"cliente_ruc": cliente_ruc}
    denegado = await access.verificar_acceso_cartera("consultar_cobranzas", args, perfil)
    t0 = time.time()
    resultado = denegado or await collections.consultar_cobranzas(args["cliente_ruc"], estado)
    await _log(perfil, "consultar_cobranzas", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_historial(
    cliente_ruc: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    meses: int = 18,
) -> Command:
    """Consulta el historial de compras de un cliente en los últimos N meses. Útil para ver tendencia y frecuencia de compra."""
    perfil = state["perfil"]
    args = {"cliente_ruc": cliente_ruc}
    denegado = await access.verificar_acceso_cartera("consultar_historial", args, perfil)
    t0 = time.time()
    resultado = denegado or await credit.consultar_historial(args["cliente_ruc"], meses)
    await _log(perfil, "consultar_historial", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def obtener_documentos(
    cliente_ruc: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    tipo: Optional[str] = None,
) -> Command:
    """Obtiene facturas, guías de remisión y notas de crédito de un cliente."""
    perfil = state["perfil"]
    args = {"cliente_ruc": cliente_ruc}
    denegado = await access.verificar_acceso_cartera("obtener_documentos", args, perfil)
    t0 = time.time()
    resultado = denegado or await documents.obtener_documentos(args["cliente_ruc"], tipo)
    await _log(perfil, "obtener_documentos", t0)
    return _to_command(resultado, tool_call_id)


# ─── Cartera (solo vendedores) ────────────────────────────────────────────────

@tool
async def consultar_cartera(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
) -> Command:
    """DEBES usar esta tool SIEMPRE que el asesor pregunte por sus clientes, su cartera o su lista de cuentas. Devuelve todos los clientes asignados a este asesor con razón social, tipo, estado, límite de crédito, saldo pendiente y último pedido. Dispárala ante frases como 'mis clientes', 'mi cartera', 'qué clientes tengo'. NO inventes ni resumas la cartera de memoria."""
    perfil = state["perfil"]
    vendedor_id = perfil.get("vendedor_id", "V001")
    t0 = time.time()
    resultado = await cartera.consultar_cartera(vendedor_id, estado, tipo)
    await _log(perfil, "consultar_cartera", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_perfil_cliente(
    ruc: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Obtiene el perfil completo de un cliente: razón social, dirección, teléfono, tipo, vendedor asignado y estado."""
    perfil = state["perfil"]
    args = {"ruc": ruc}
    denegado = await access.verificar_acceso_cartera("consultar_perfil_cliente", args, perfil)
    t0 = time.time()
    resultado = denegado or await cartera.consultar_perfil_cliente(args["ruc"])
    await _log(perfil, "consultar_perfil_cliente", t0)
    return _to_command(resultado, tool_call_id)


# ─── Catálogo / vehículo ──────────────────────────────────────────────────────

@tool
async def buscar_catalogo(
    query: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    placa: Optional[str] = None,
    vin: Optional[str] = None,
) -> Command:
    """Busca productos en el catálogo por nombre, categoría o placa/VIN del vehículo. Usar para encontrar repuestos, ver equivalencias o buscar productos compatibles."""
    perfil = state["perfil"]
    t0 = time.time()
    resultado = await catalog_rag.buscar_catalogo(query, placa, vin)
    await _log(perfil, "buscar_catalogo", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def identificar_vehiculo(
    placa_o_vin: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Busca en el CATÁLOGO INTERNO los repuestos compatibles con un vehículo a partir de su placa o VIN (datos de catálogo, no oficiales). NO uses esta tool para saber 'qué auto es' una placa: para identificar el vehículo de una placa peruana usa consultar_placa_sunarp. Usa esta SOLO cuando ya sabes el vehículo y quieres ver qué repuestos le calzan."""
    perfil = state["perfil"]
    t0 = time.time()
    resultado = await vehicle.identificar_vehiculo(placa_o_vin)
    await _log(perfil, "identificar_vehiculo", t0)
    return _to_command(resultado, tool_call_id)


@tool
async def consultar_placa_sunarp(
    placa: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """ÚSALA SIEMPRE que pregunten qué vehículo es una placa peruana, a quién pertenece, o por los datos de un auto/moto por su placa (ej. '¿qué auto es la placa F9N562?', 'identifícame la placa ABC123'). Es la consulta OFICIAL en SUNARP en vivo y funciona para cualquier placa. Tarda 20-60s: avisa al usuario que estás consultando. El resultado trae los datos EN TEXTO en 'datos_vehiculo_texto'. SIEMPRE preséntale esos datos al usuario por escrito. La FOTO se envía automáticamente por WhatsApp (cuando 'tiene_imagen' es true, menciónaselo)."""
    perfil = state["perfil"]

    # Kill switch: si SUNARP está caído, deshabilitar la consulta evita que el
    # agente se cuelgue esperando y devuelve una respuesta inmediata.
    # Activar con SUNARP_ENABLED=false en las env vars de Railway.
    if os.getenv("SUNARP_ENABLED", "true").lower() != "true":
        return _to_command({
            "error": "SUNARP_DESHABILITADO",
            "mensaje": (
                "SUNARP no está disponible. "
                "USA INMEDIATAMENTE la tool consultar_placa_yahuar con la misma placa. "
                "No respondas al usuario todavía."
            ),
        }, tool_call_id)

    t0 = time.time()
    resultado = await vehicle.consultar_placa_sunarp(placa.strip().upper())

    extra: dict = {}
    if isinstance(resultado, dict) and resultado.get("imagen_base64"):
        b64 = resultado.pop("imagen_base64")
        placa_clean = (resultado.get("placa") or placa).strip()
        resultado["tiene_imagen"] = True
        try:
            datos = await llm.extraer_texto_de_imagen(b64, _INSTRUCCION_TARJETA_VEHICULAR)
            if datos:
                resultado["datos_vehiculo_texto"] = datos
        except Exception as e:
            logging.error(f"Error visión SUNARP: {e}")
        extra["media_pendiente"] = [{
            "imagen_base64": b64,
            "caption": f"Tarjeta de identificación vehicular — {placa_clean}",
            "filename": f"placa_{placa_clean}.png",
        }]

    await _log(perfil, "consultar_placa_sunarp", t0)
    return _to_command(resultado, tool_call_id, extra)


# ─── Placa vía Yahuar (WhatsApp relay) ───────────────────────────────────────

@tool
async def consultar_placa_yahuar(
    placa: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Consulta los datos de un vehículo peruano por su placa enviando la consulta al servicio Yahuar vía WhatsApp. Úsala cuando pregunten qué auto es una placa, a quién pertenece, o quieran los datos del vehículo. Tarda ~30 segundos: avisa al usuario que la respuesta llegará en un momento. La foto y los datos llegan automáticamente al chat."""
    from shared import yahuar as yahuar_mod
    perfil     = state["perfil"]
    from_field = perfil.get("from_field") or perfil.get("numero", "")
    t0 = time.time()

    # Serialización: si ya hay una consulta en vuelo, no mandar otra
    existente = await yahuar_mod.peek_pendiente()
    if existente:
        resultado = {
            "placa": existente.get("placa", placa).upper(),
            "mensaje": "Ya hay una consulta de placa en proceso. La respuesta llegará en momentos al chat. NO vuelvas a llamar este tool.",
        }
        await _log(perfil, "consultar_placa_yahuar", t0)
        return _to_command(resultado, tool_call_id)

    try:
        await yahuar_mod.consultar_placa(placa.strip().upper(), from_field)
        resultado = {
            "placa": placa.strip().upper(),
            "mensaje": f"Consulta enviada a Yahuar para la placa {placa.strip().upper()}. La respuesta llega en ~30 segundos directamente al chat. NO llames este tool de nuevo.",
        }
    except Exception as e:
        logging.error(f"Error consultando Yahuar: {e}")
        resultado = {"error": "YAHUAR_ERROR", "mensaje": "No pude consultar la placa en este momento. Inténtalo de nuevo."}
    await _log(perfil, "consultar_placa_yahuar", t0)
    return _to_command(resultado, tool_call_id)


# ─── Solo clientes ────────────────────────────────────────────────────────────

@tool
async def registrar_reclamo(
    pedido_id: str,
    motivo: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Registra un reclamo o queja del cliente y genera un número de caso."""
    perfil = state["perfil"]
    conv_id = perfil.get("conversation_id", "mock")
    t0 = time.time()
    resultado = await claims.registrar_reclamo(conv_id, pedido_id, motivo)
    await _log(perfil, "registrar_reclamo", t0)
    return _to_command(resultado, tool_call_id)


# ─── Toolsets por canal ───────────────────────────────────────────────────────

# NOTA: al migrar del Mock SAP a la API real de Catusita (tools-agente-catusita),
# se APAGARON las tools sin dato de origen real: buscar_pedido_por_id,
# consultar_pedidos, consultar_credito, consultar_cobranzas, consultar_historial,
# obtener_documentos e identificar_vehiculo. Sus @tool y wrappers en agents/ siguen
# definidos pero NO se exponen al modelo. Ver docs/plan_migracion_api_real.md.
TOOLS_VENDEDOR_LC = [
    consultar_stock,
    consultar_precio,
    consultar_pedidos,
    consultar_despacho,
    consultar_cartera,
    consultar_perfil_cliente,
    buscar_catalogo,
    consultar_placa_sunarp,
    consultar_placa_yahuar,
]

TOOLS_CLIENTE_LC = [
    consultar_stock,
    consultar_precio,
    buscar_catalogo,
    consultar_placa_sunarp,
    registrar_reclamo,
]
