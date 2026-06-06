import json
import logging
import time
from shared import llm
from db import models
from agents import stock, prices, orders, credit, documents, catalog_rag, vehicle, collections, claims, cartera

# ---------------------------------------------------------------------------
# Definición de tools
# ---------------------------------------------------------------------------

TOOLS_VENDEDORES = [
    {
        "name": "consultar_stock",
        "description": "Consulta el stock disponible de un producto en los almacenes. Usar cuando pregunten por disponibilidad, inventario o si hay stock de un producto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string", "description": "Código SKU del producto. Ej: FIL-BOC-4521"},
            },
            "required": ["sku_code"],
        },
    },
    {
        "name": "consultar_precio",
        "description": "Consulta el precio de lista de un producto. El agente de vendedores SOLO muestra precio de lista, nunca precios netos ni descuentos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string", "description": "Código SKU del producto"},
            },
            "required": ["sku_code"],
        },
    },
    {
        "name": "consultar_pedidos",
        "description": "Consulta los pedidos de un cliente por su RUC. Muestra estado, fechas de entrega y tracking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_ruc": {"type": "string", "description": "RUC del cliente. Ej: 20123456789"},
                "estado": {"type": "string", "description": "Filtrar por estado: en_almacen, en_transito, entregado, con_incidencia"},
            },
            "required": ["cliente_ruc"],
        },
    },
    {
        "name": "consultar_credito",
        "description": "Consulta el límite de crédito, saldo usado y saldo disponible de un cliente. Solo para asesores comerciales.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_ruc": {"type": "string", "description": "RUC del cliente"},
            },
            "required": ["cliente_ruc"],
        },
    },
    {
        "name": "consultar_cobranzas",
        "description": "Consulta las letras, facturas vencidas y deuda pendiente de un cliente. Usar para revisar estado de cobranza.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_ruc": {"type": "string", "description": "RUC del cliente"},
                "estado": {"type": "string", "description": "Filtrar por estado: pendiente, vencida, pagada"},
            },
            "required": ["cliente_ruc"],
        },
    },
    {
        "name": "consultar_historial",
        "description": "Consulta el historial de compras de un cliente en los últimos N meses. Útil para ver tendencia y frecuencia de compra.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_ruc": {"type": "string", "description": "RUC del cliente"},
                "meses": {"type": "integer", "description": "Cantidad de meses hacia atrás (default: 18)"},
            },
            "required": ["cliente_ruc"],
        },
    },
    {
        "name": "obtener_documentos",
        "description": "Obtiene facturas, guías de remisión y notas de crédito de un cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_ruc": {"type": "string", "description": "RUC del cliente"},
                "tipo": {"type": "string", "description": "Tipo de documento: factura, guia, nc. Si no se especifica devuelve todos."},
            },
            "required": ["cliente_ruc"],
        },
    },
    {
        "name": "consultar_cartera",
        "description": "DEBES usar esta tool SIEMPRE que el asesor pregunte por sus clientes, su cartera o su lista de cuentas. Devuelve todos los clientes asignados a este asesor con razón social, tipo, estado, límite de crédito, saldo pendiente y último pedido. Dispárala ante frases como 'mis clientes', 'mi cartera', 'qué clientes tengo', 'lista de mis cuentas', 'a quién le vendo' o cualquier consulta sobre el conjunto de clientes del asesor. NO inventes ni resumas la cartera de memoria: obtén siempre los datos con esta tool antes de responder. Acepta filtros opcionales por estado y tipo de cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "estado": {"type": "string", "description": "Filtrar por estado del cliente: activo, suspendido, bloqueado"},
                "tipo": {"type": "string", "description": "Filtrar por tipo: taller, distribuidor, consumidor_final"},
            },
        },
    },
    {
        "name": "consultar_perfil_cliente",
        "description": "Obtiene el perfil completo de un cliente: razón social, dirección, teléfono, tipo, vendedor asignado y estado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ruc": {"type": "string", "description": "RUC del cliente. Ej: 20123456789"},
            },
            "required": ["ruc"],
        },
    },
    {
        "name": "buscar_catalogo",
        "description": "Busca productos en el catálogo por nombre, categoría o placa/VIN del vehículo. Usar para encontrar repuestos, ver equivalencias o buscar productos compatibles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Búsqueda en lenguaje natural. Ej: 'filtro de aceite Toyota'"},
                "placa": {"type": "string", "description": "Placa del vehículo para buscar repuestos compatibles. Ej: ABC-123"},
                "vin": {"type": "string", "description": "VIN del vehículo (17 caracteres)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "identificar_vehiculo",
        "description": "Identifica marca, modelo y año de un vehículo por su placa o VIN. Devuelve también repuestos compatibles disponibles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "placa_o_vin": {"type": "string", "description": "Placa (formato ABC-123) o VIN (17 caracteres)"},
            },
            "required": ["placa_o_vin"],
        },
    },
    {
        "name": "consultar_placa_sunarp",
        "description": "Consulta oficial en SUNARP por placa peruana. Tarda 20-60s, avisa al usuario que estás consultando. IMPORTANTE: el resultado en texto SOLO trae datos registrales (oficina registral y número de partida). Los datos del vehículo (marca, modelo, año, color, VIN, motor, propietario) vienen DENTRO de la foto de la tarjeta de identificación vehicular, que se envía automáticamente al usuario por WhatsApp. Cuando el resultado tenga 'tiene_imagen': true, dile al usuario que esos datos están en la foto de la tarjeta que le acabas de enviar. NUNCA ofrezcas 'hacer una consulta más detallada' de marca/modelo/año/propietario: esa consulta no existe, los datos están en la foto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "placa": {"type": "string", "description": "Placa del vehículo a consultar. Ej: 'F9N562'"},
            },
            "required": ["placa"],
        },
    },
]

TOOLS_CLIENTES = [
    {
        "name": "consultar_stock",
        "description": "Consulta si un producto está disponible en stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string", "description": "Código SKU del producto"},
            },
            "required": ["sku_code"],
        },
    },
    {
        "name": "consultar_precio",
        "description": "Consulta el precio de lista de un producto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string", "description": "Código SKU del producto"},
            },
            "required": ["sku_code"],
        },
    },
    {
        "name": "consultar_pedidos",
        "description": "Consulta el estado de los pedidos propios del cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_ruc": {"type": "string", "description": "RUC del cliente"},
                "estado": {"type": "string", "description": "Filtrar por estado del pedido"},
            },
            "required": ["cliente_ruc"],
        },
    },
    {
        "name": "obtener_documentos",
        "description": "Obtiene facturas y guías de remisión propias del cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_ruc": {"type": "string", "description": "RUC del cliente"},
                "tipo": {"type": "string", "description": "Tipo: factura, guia, nc"},
            },
            "required": ["cliente_ruc"],
        },
    },
    {
        "name": "buscar_catalogo",
        "description": "Busca productos en el catálogo o repuestos compatibles con un vehículo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Búsqueda en lenguaje natural"},
                "placa": {"type": "string", "description": "Placa del vehículo"},
                "vin": {"type": "string", "description": "VIN del vehículo"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "identificar_vehiculo",
        "description": "Identifica un vehículo por placa o VIN.",
        "input_schema": {
            "type": "object",
            "properties": {
                "placa_o_vin": {"type": "string", "description": "Placa o VIN del vehículo"},
            },
            "required": ["placa_o_vin"],
        },
    },
    {
        "name": "consultar_placa_sunarp",
        "description": "Consulta oficial en SUNARP por placa peruana. Tarda 20-60s, avisa al usuario que estás consultando. IMPORTANTE: el resultado en texto SOLO trae datos registrales (oficina y partida). Los datos del vehículo (marca, modelo, año, color, VIN, motor, propietario) vienen DENTRO de la foto de la tarjeta vehicular, que se envía automáticamente por WhatsApp. Cuando el resultado tenga 'tiene_imagen': true, dile al usuario que esos datos están en la foto que le acabas de enviar. NUNCA ofrezcas una 'consulta más detallada': no existe, los datos están en la foto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "placa": {"type": "string", "description": "Placa del vehículo a consultar. Ej: 'F9N562'"},
            },
            "required": ["placa"],
        },
    },
    {
        "name": "registrar_reclamo",
        "description": "Registra un reclamo o queja del cliente y genera un número de caso.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_id": {"type": "string", "description": "Número de pedido relacionado"},
                "motivo": {"type": "string", "description": "Descripción del reclamo"},
            },
            "required": ["pedido_id", "motivo"],
        },
    },
]

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_VENDEDOR = """Eres el asistente de IA de Grupo Catusita para asesores comerciales.
Tu nombre es Catu. Tienes acceso a información de SAP: stock, precios de lista, pedidos,
crédito de clientes, facturas, guías, cobranzas, cartera de clientes y catálogo de productos.

Reglas importantes:
- Responde siempre en español, de forma concisa y directa (máx. 3-4 líneas por sección)
- Usa emojis con moderación (✅ ⚠️ 🚚 📄 💰)
- NUNCA inventes precios, stocks ni fechas — siempre usa las tools
- SOLO muestra precio de lista. Nunca menciones precios netos, descuentos ni condiciones especiales
- Si el asesor pregunta por precio neto o descuentos, responde: "Los precios netos se coordinan directamente con tu jefe de línea"
- Solo puedes consultar clientes de la cartera asignada a este asesor
- SIEMPRE que el asesor pregunte por sus clientes, su cartera, su lista de cuentas o a quién le vende (ej. "mis clientes", "mi cartera", "qué clientes tengo"), DEBES llamar a la tool consultar_cartera antes de responder. Nunca enumeres ni resumas la cartera de memoria
- Cuando el asesor mencione un cliente por nombre parcial (ej: 'Repuestos Razo', 'Taller Aguilera'), NUNCA le pidas el RUC. En su lugar: (1) llama a consultar_cartera para obtener la lista de clientes, (2) identifica el cliente que más se parece al nombre mencionado, (3) usa su RUC automáticamente para las consultas siguientes. Solo pide el RUC o la razon social completa si hay dos o más clientes con nombres muy similares y no puedes distinguirlos.
- Si una consulta requiere múltiples tools, ejecútalas todas antes de responder
- Si la consulta excede tus permisos o no tienes información suficiente, deriva al área correspondiente

El asesor {nombre} tiene asignada la línea: {linea_asignada}
ID del vendedor: {vendedor_id}"""

SYSTEM_CLIENTE = """Eres el asistente de IA de Grupo Catusita para clientes.
Tu nombre es Catu. Puedes ayudar con: consulta de stock y precios de lista,
estado de pedidos y facturas, búsqueda de productos, equivalencias y reclamos.

Reglas:
- Responde siempre en español, de forma amigable y clara
- Solo muestras precios de lista (nunca precios netos o condiciones de crédito)
- Si el cliente quiere hacer un pedido, dile que contacte a su asesor de ventas
- Para reclamos, registra el reclamo y dile que lo enviaras a atención al cliente para que se contacten con él
- Nunca inventes información — siempre usa las tools disponibles"""

# ---------------------------------------------------------------------------
# Dispatch de tools
# ---------------------------------------------------------------------------

async def execute_tool(name: str, args: dict, perfil: dict) -> dict:
    conv_id = perfil.get("conversation_id", "mock-conv-id")
    vendedor_id = perfil.get("vendedor_id", "V001")

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
