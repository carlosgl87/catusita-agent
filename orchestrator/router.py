import json
from shared import llm
from agents import stock, prices, orders, credit, documents, catalog_rag, vehicle, collections, claims

# ---------------------------------------------------------------------------
# Definición de tools
# ---------------------------------------------------------------------------

TOOLS_VENDEDORES = [
    {
        "name": "consultar_stock",
        "description": "Consulta el stock disponible de un producto en los almacenes. Usar cuando pregunten por disponibilidad, inventario o si hay un producto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string", "description": "Código SKU del producto"},
                "almacen_id": {"type": "integer", "description": "0=ambos, 1=Miraflores, 2=Ate"},
            },
            "required": ["sku_code"],
        },
    },
    {
        "name": "consultar_precio",
        "description": "Consulta el precio neto según tipo de cliente y escala de descuentos por volumen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string"},
                "tipo_cliente": {"type": "string", "enum": ["tienda", "taller", "consumidor"]},
                "cantidad": {"type": "integer", "description": "Cantidad para calcular descuento por volumen"},
                "zona": {"type": "string", "description": "Zona del cliente: Lima o provincia"},
            },
            "required": ["sku_code", "tipo_cliente"],
        },
    },
    {
        "name": "consultar_pedido",
        "description": "Consulta el estado y ubicación de un pedido en tiempo real.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_id": {"type": "string"},
                "ruc_cliente": {"type": "string", "description": "Alternativo al pedido_id"},
            },
        },
    },
    {
        "name": "consultar_credito",
        "description": "Consulta límite de crédito, saldo disponible, deuda e historial de letras de un cliente. Solo para asesores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {"type": "string", "description": "RUC o código SAP del cliente"},
            },
            "required": ["cliente_id"],
        },
    },
    {
        "name": "obtener_documentos",
        "description": "Obtiene facturas, guías de remisión y notas de crédito de un cliente en PDF o XML.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {"type": "string"},
                "pedido_id": {"type": "string", "description": "Opcional, para un pedido específico"},
                "tipo_doc": {"type": "string", "enum": ["factura", "guia", "nc", "todos"]},
                "formato": {"type": "string", "enum": ["pdf", "xml", "ambos"]},
            },
            "required": ["cliente_id"],
        },
    },
    {
        "name": "buscar_catalogo",
        "description": "Busca productos en el catálogo por descripción, síntoma o compatibilidad. Usar para equivalencias, fichas técnicas y búsqueda semántica.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Búsqueda en lenguaje natural"},
                "placa": {"type": "string", "description": "Placa del vehículo (opcional)"},
                "vin": {"type": "string", "description": "VIN del vehículo (opcional)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "identificar_vehiculo",
        "description": "Identifica marca, modelo y año de un vehículo a partir de su placa o VIN.",
        "input_schema": {
            "type": "object",
            "properties": {
                "placa": {"type": "string"},
                "vin": {"type": "string"},
            },
        },
    },
    {
        "name": "consultar_letras_proximas",
        "description": "Muestra qué clientes de la cartera tienen letras por vencer en los próximos días.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {"type": "integer", "description": "Días hacia adelante (default: 7)"},
            },
        },
    },
    {
        "name": "reporte_cobranzas",
        "description": "Genera el reporte de cobranzas de la cartera del asesor para una semana.",
        "input_schema": {
            "type": "object",
            "properties": {
                "semana": {"type": "string", "description": "Semana en formato YYYY-WNN (opcional)"},
            },
        },
    },
    {
        "name": "consultar_antiguedad_stock",
        "description": "Muestra productos con más días en almacén para priorizar su venta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dias_minimos": {"type": "integer", "description": "Días mínimos en almacén (default: 90)"},
                "almacen_id": {"type": "integer", "description": "0=ambos, 1=Miraflores, 2=Ate"},
            },
        },
    },
]

TOOLS_CLIENTES = [
    {
        "name": "consultar_stock",
        "description": "Consulta el stock disponible de un producto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string"},
                "almacen_id": {"type": "integer", "description": "0=ambos, 1=Miraflores, 2=Ate"},
            },
            "required": ["sku_code"],
        },
    },
    {
        "name": "consultar_pedido",
        "description": "Consulta el estado de un pedido del cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_id": {"type": "string"},
                "ruc_cliente": {"type": "string"},
            },
        },
    },
    {
        "name": "obtener_documentos",
        "description": "Obtiene facturas y guías del propio cliente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {"type": "string"},
                "pedido_id": {"type": "string"},
                "tipo_doc": {"type": "string", "enum": ["factura", "guia", "nc", "todos"]},
                "formato": {"type": "string", "enum": ["pdf", "xml", "ambos"]},
            },
            "required": ["cliente_id"],
        },
    },
    {
        "name": "buscar_catalogo",
        "description": "Busca productos en el catálogo, equivalencias y fichas técnicas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "placa": {"type": "string"},
                "vin": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "identificar_vehiculo",
        "description": "Identifica el vehículo por placa o VIN.",
        "input_schema": {
            "type": "object",
            "properties": {
                "placa": {"type": "string"},
                "vin": {"type": "string"},
            },
        },
    },
    {
        "name": "registrar_reclamo",
        "description": "Registra una queja o reclamo del cliente y genera un número de caso.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_id": {"type": "string", "description": "Número de pedido involucrado"},
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
Tu nombre es Catu. Tienes acceso completo a información de SAP: stock, precios netos,
crédito de clientes, facturas, guías, cobranzas y catálogo de productos.

Reglas:
- Responde siempre en español, de forma concisa y directa (máx. 3-4 líneas por sección)
- Usa emojis con moderación para mejorar la lectura (✅ ⚠️ 🚚 📄)
- Si te preguntan por información que requiere una tool, úsala antes de responder
- Nunca inventes precios, stocks ni fechas — siempre usa las tools
- Si una consulta requiere múltiples tools, ejecútalas todas antes de responder
- El asesor {nombre} tiene asignada la línea: {linea_asignada}"""

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
    asesor_id = perfil.get("asesor_id", "ASE-001")

    dispatch = {
        "consultar_stock": lambda: stock.consultar_stock(
            args["sku_code"], args.get("almacen_id", 0)
        ),
        "consultar_precio": lambda: prices.consultar_precio(
            args["sku_code"], args["tipo_cliente"],
            asesor_id, args.get("cantidad", 1), args.get("zona")
        ),
        "consultar_pedido": lambda: orders.consultar_pedido(
            args.get("pedido_id"), args.get("ruc_cliente")
        ),
        "consultar_credito": lambda: credit.consultar_credito(args["cliente_id"]),
        "obtener_documentos": lambda: documents.obtener_documentos(
            args["cliente_id"], args.get("pedido_id"),
            args.get("tipo_doc", "todos"), args.get("formato", "pdf")
        ),
        "buscar_catalogo": lambda: catalog_rag.buscar_catalogo(
            args["query"], args.get("placa"), args.get("vin")
        ),
        "identificar_vehiculo": lambda: vehicle.identificar_vehiculo(
            args.get("placa"), args.get("vin")
        ),
        "consultar_letras_proximas": lambda: collections.consultar_letras_proximas(
            asesor_id, args.get("dias", 7)
        ),
        "reporte_cobranzas": lambda: collections.reporte_cobranzas(
            asesor_id, args.get("semana")
        ),
        "consultar_antiguedad_stock": lambda: stock.consultar_antiguedad(
            args.get("almacen_id", 0), args.get("dias_minimos", 90)
        ),
        "registrar_reclamo": lambda: claims.registrar_reclamo(
            conv_id, args["pedido_id"], args["motivo"]
        ),
    }

    fn = dispatch.get(name)
    if fn is None:
        return {"error": f"Tool desconocida: {name}"}
    return await fn()


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
