"""Orquestador del agente: dispatch de tools y loop de tool-use con Claude.

- Las definiciones de tools viven en orchestrator/tools.py
- Los system prompts viven en orchestrator/prompts.py
- El control de acceso por cartera vive en orchestrator/access.py
"""
import json
import logging
import time

from shared import llm
from shared.sap_client import sap
from db import models
from agents import (
    stock, prices, orders, credit, documents,
    catalog_rag, vehicle, collections, claims, cartera,
)
from orchestrator import access
from orchestrator.tools import TOOLS_VENDEDORES, TOOLS_CLIENTES
from orchestrator.prompts import SYSTEM_VENDEDOR, SYSTEM_CLIENTE


# ---------------------------------------------------------------------------
# Post-procesamiento de resultados de tools
# ---------------------------------------------------------------------------

async def _sugerencias_si_sku_invalido(name: str, args: dict, resultado: dict) -> dict | None:
    """Si una consulta de stock/precio falló por SKU inexistente, busca en el
    catálogo coincidencias parciales y las devuelve como sugerencias. Retorna
    None si no aplica (la tool siguió su curso normal)."""
    if name not in ("consultar_stock", "consultar_precio") or not isinstance(resultado, dict):
        return None
    if not ("error" in resultado or resultado.get("detail") == "Producto no encontrado"):
        return None

    sku_query = args.get("sku_code", "").strip()
    if not sku_query:
        return None

    try:
        search_res = await sap.get_catalogo(q=sku_query)
        productos = search_res.get("productos", []) if isinstance(search_res, dict) else []
    except Exception:
        productos = []

    if not productos:
        return None

    return {
        "error": "PRODUCTO_NO_ENCONTRADO_SUGERENCIAS",
        "mensaje": (
            f"No se encontró ningún producto con el SKU exacto '{sku_query}'. "
            "Sin embargo, encontramos estas coincidencias en el catálogo. "
            "Por favor, pregúntale al usuario si se refiere a alguna de estas opciones y muéstrale los SKUs y nombres correspondientes."
        ),
        "sugerencias": [
            {"sku": p["sku"], "nombre": p["nombre"], "categoria": p.get("categoria"), "marca": p.get("marca")}
            for p in productos[:5]
        ],
    }


# ---------------------------------------------------------------------------
# Dispatch de tools
# ---------------------------------------------------------------------------

async def execute_tool(name: str, args: dict, perfil: dict) -> dict:
    conv_id = perfil.get("conversation_id", "mock-conv-id")
    vendedor_id = perfil.get("vendedor_id", "V001")

    # --- Control de acceso por cartera (solo asesores) ---
    # Antes de tocar el Mock SAP, validar que el RUC consultado sea de la
    # cartera del asesor. No confiar solo en el system prompt.
    denegado = await access.verificar_acceso_cartera(name, args, perfil)
    if denegado is not None:
        return denegado

    dispatch = {
        "consultar_stock": lambda: stock.consultar_stock(
            args["sku_code"]
        ),
        "consultar_precio": lambda: prices.consultar_precio(
            args["sku_code"], tipo="lista"  # siempre precio lista
        ),
        "consultar_pedidos": lambda: orders.consultar_pedidos(
            args["cliente_ruc"], args.get("estado")
        ),
        "consultar_credito": lambda: credit.consultar_credito(
            args["cliente_ruc"]
        ),
        "consultar_cobranzas": lambda: collections.consultar_cobranzas(
            args["cliente_ruc"], args.get("estado")
        ),
        "consultar_historial": lambda: credit.consultar_historial(
            args["cliente_ruc"], args.get("meses", 18)
        ),
        "obtener_documentos": lambda: documents.obtener_documentos(
            args["cliente_ruc"], args.get("tipo")
        ),
        "consultar_cartera": lambda: cartera.consultar_cartera(
            vendedor_id, args.get("estado"), args.get("tipo")
        ),
        "consultar_perfil_cliente": lambda: cartera.consultar_perfil_cliente(
            args["ruc"]
        ),
        "buscar_catalogo": lambda: catalog_rag.buscar_catalogo(
            args["query"], args.get("placa"), args.get("vin")
        ),
        "identificar_vehiculo": lambda: vehicle.identificar_vehiculo(
            args["placa_o_vin"]
        ),
        "consultar_placa_sunarp": lambda: vehicle.consultar_placa_sunarp(
            args["placa"]
        ),
        "registrar_reclamo": lambda: claims.registrar_reclamo(
            conv_id, args["pedido_id"], args["motivo"]
        ),
    }

    fn = dispatch.get(name)
    if fn is None:
        return {"error": f"Tool desconocida: {name}"}

    inicio = time.time()
    resultado = await fn()
    duracion_ms = int((time.time() - inicio) * 1000)

    # --- Fallback: si el SKU no existe, sugerir productos del catálogo ---
    sugerencia = await _sugerencias_si_sku_invalido(name, args, resultado)
    if sugerencia is not None:
        return sugerencia

    # ------------------------------------------------------------------
    # Media (imagen base64) → no debe llegar al LLM. Se extrae y se encola
    # en el perfil para que el webhook la envíe por WhatsApp como foto.
    # ------------------------------------------------------------------
    if isinstance(resultado, dict) and resultado.get("imagen_base64"):
        b64 = resultado.pop("imagen_base64")
        placa = (resultado.get("placa") or args.get("placa") or "").strip()
        perfil.setdefault("_media_pendiente", []).append({
            "imagen_base64": b64,
            "caption": f"Tarjeta de identificación vehicular{' — ' + placa if placa else ''}",
            "filename": f"placa_{placa or 'vehiculo'}.png",
        })
        resultado["tiene_imagen"] = True

    # Registro de uso de tools (best-effort: no debe romper el flujo)
    try:
        await models.log_tool_usage(conv_id, vendedor_id, name, duracion_ms)
    except Exception as e:
        logging.error(f"Error guardando en DB: {e}", exc_info=True)
        print(f"Error guardando en DB (tool_usage): {e}")

    return resultado


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

async def run_agent(mensaje: str, perfil: dict, historial: list) -> str:
    es_asesor = perfil.get("tipo") == "asesor"
    tools = TOOLS_VENDEDORES if es_asesor else TOOLS_CLIENTES
    system = (
        SYSTEM_VENDEDOR.format(
            nombre=perfil.get("nombre", "Asesor"),
            linea_asignada=perfil.get("linea_asignada", "general"),
            vendedor_id=perfil.get("vendedor_id", "V001"),
        )
        if es_asesor
        else SYSTEM_CLIENTE
    )

    messages = historial + [{"role": "user", "content": mensaje}]

    while True:
        response = await llm.create_message(
            system=system,
            tools=tools,
            messages=messages,
            max_tokens=2048,
        )

        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return text_blocks[0] if text_blocks else ""

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    resultado = await execute_tool(block.name, block.input, perfil)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(resultado, ensure_ascii=False, default=str),
                    })

            messages.append({"role": "user", "content": tool_results})
        else:
            # stop_reason inesperado
            break

    return "No pude procesar tu consulta en este momento. Inténtalo de nuevo."
