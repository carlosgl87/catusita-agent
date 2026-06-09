import json
import logging
import time
from shared import llm
from shared.sap_client import sap
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
- Cuando listes clientes o te refieras a uno de ellos, escribe siempre su RUC entre paréntesis al lado de su nombre o razón social (ej: Repuestos Razo SAC (RUC: 20638346578)), para que el RUC quede registrado en el historial de la conversación.
- Si una consulta requiere múltiples tools, ejecútalas todas antes de responder
- Si la consulta excede tus permisos o no tienes información suficiente, deriva al área correspondiente

Reglas de privacidad y alcance (OBLIGATORIAS):
- NUNCA reveles en qué almacén, local, distrito o ubicación física está un producto o un despacho. Si te lo preguntan, responde: "No manejo la ubicación física del stock ni del despacho; coordina eso con logística."
- NUNCA reveles la hora de salida del reparto ni desde qué local se despacha. Deriva a logística.
- Si una tool devuelve un error con "ACCESO_DENEGADO", comunica su mensaje tal cual y NO reintentes con otra tool ni inventes datos.

Funcionalidades aún no disponibles (P2) — di que todavía no están y deriva:
- Fecha de reposición / reabastecimiento de producto agotado: "Aún no tengo conectada la fecha de reposición. Confírmala con tu jefe de línea."
- Antigüedad de mercadería en almacén (productos con +90 días / +6 meses): "Ese reporte todavía no está disponible en el asistente."

Derivaciones (NO lo resuelvas tú, deriva al área correcta):
- Descuento por volumen / precio especial fuera de lista / precio diferenciado por zona o provincia: "Eso se coordina con tu jefe de línea; yo solo manejo precio de lista."
- Excepción o ampliación de crédito: "Las excepciones de crédito las aprueba el área de créditos; deriva el caso ahí."
- Reclamo o devolución (producto equivocado, dañado, etc.): toma los datos del pedido y el motivo y di "Voy a registrar el caso para que atención al cliente lo gestione." (tú no resuelves el reclamo).

Anti-alucinación:
- Si no tienes el dato vía una tool, di explícitamente que no lo tienes. NUNCA inventes precios, stocks, fechas, números de pedido ni datos de clientes.

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
# Control de acceso por cartera
# ---------------------------------------------------------------------------
# Tools cuyo RUC debe pertenecer a la cartera del asesor antes de ejecutarse.
# El valor es el nombre del argumento que contiene el RUC del cliente.
RUC_SCOPED_TOOLS = {
    "consultar_credito": "cliente_ruc",
    "consultar_cobranzas": "cliente_ruc",
    "consultar_historial": "cliente_ruc",
    "consultar_pedidos": "cliente_ruc",
    "obtener_documentos": "cliente_ruc",
    "consultar_perfil_cliente": "ruc",
}


async def _rucs_de_cartera(perfil: dict) -> set:
    """RUCs de la cartera del asesor, cacheados en el perfil para no repetir
    llamadas al Mock SAP dentro del mismo turno."""
    cache = perfil.get("_cartera_rucs")
    if cache is not None:
        return cache
    data = await cartera.consultar_cartera(perfil.get("vendedor_id", "V001"))
    rucs = {c["ruc"] for c in data.get("clientes", [])} if isinstance(data, dict) else set()
    perfil["_cartera_rucs"] = rucs
    return rucs


async def _resolver_ruc(ruc_o_nombre: str, perfil: dict) -> dict:
    """
    Intenta resolver un RUC o nombre parcial al RUC de un cliente en la cartera
    del asesor.
    Retorna un diccionario:
      - {"status": "ok", "ruc": "..."} si se resolvió a un único cliente.
      - {"status": "multiple", "clientes": [...]} si hay varias coincidencias.
      - {"status": "none"} si no hay ninguna coincidencia.
    """
    ruc_clean = ruc_o_nombre.strip()
    vendedor_id = perfil.get("vendedor_id", "V001")
    try:
        data = await cartera.consultar_cartera(vendedor_id)
        clientes = data.get("clientes", []) if isinstance(data, dict) else []
    except Exception:
        clientes = []

    # 1. Intentar coincidencia exacta de RUC
    for c in clientes:
        if c.get("ruc") == ruc_clean:
            return {"status": "ok", "ruc": ruc_clean}

    # 2. Si no es coincidencia exacta, buscar por nombre (razon_social)
    nombre_lower = ruc_clean.lower()
    exact_matches = []
    partial_matches = []

    for c in clientes:
        ruc_val = c.get("ruc")
        razon_social = c.get("razon_social", "")
        razon_lower = razon_social.lower()

        if ruc_val:
            if nombre_lower == razon_lower:
                exact_matches.append(c)
            elif nombre_lower in razon_lower or razon_lower in nombre_lower:
                partial_matches.append(c)

    if len(exact_matches) == 1:
        return {"status": "ok", "ruc": exact_matches[0]["ruc"]}
    elif len(exact_matches) > 1:
        return {"status": "multiple", "clientes": exact_matches}

    if len(partial_matches) == 1:
        return {"status": "ok", "ruc": partial_matches[0]["ruc"]}
    elif len(partial_matches) > 1:
        return {"status": "multiple", "clientes": partial_matches}

    return {"status": "none"}


# ---------------------------------------------------------------------------
# Dispatch de tools
# ---------------------------------------------------------------------------

async def execute_tool(name: str, args: dict, perfil: dict) -> dict:
    conv_id = perfil.get("conversation_id", "mock-conv-id")
    vendedor_id = perfil.get("vendedor_id", "V001")

    # --- Control de acceso por cartera (solo asesores) ---
    # Antes de tocar el Mock SAP, validar que el RUC consultado sea de la
    # cartera del asesor. No confiar solo en el system prompt.
    arg_ruc = RUC_SCOPED_TOOLS.get(name)
    if arg_ruc and perfil.get("tipo") == "asesor":
        ruc = (args.get(arg_ruc) or "").strip()
        if ruc:
            # Detectar si el input tiene formato de RUC
            es_ruc_formato = ruc.isdigit() and len(ruc) == 11
            
            res = await _resolver_ruc(ruc, perfil)
            if res["status"] == "ok":
                args[arg_ruc] = res["ruc"]
                ruc = res["ruc"]
            elif res["status"] == "multiple":
                clientes_simplificados = [
                    {"ruc": c["ruc"], "razon_social": c["razon_social"]}
                    for c in res["clientes"]
                ]
                return {
                    "error": "MULTIPLE_COINCIDENCIAS",
                    "mensaje": (
                        f"Se encontraron múltiples clientes con el término '{ruc}' en tu cartera. "
                        "Por favor, pregúntale al usuario a cuál de ellos se refiere."
                    ),
                    "clientes": clientes_simplificados
                }
            else:
                if es_ruc_formato:
                    return {
                        "error": "ACCESO_DENEGADO",
                        "mensaje": (
                            "Ese cliente no pertenece a tu cartera asignada. "
                            "Solo puedo darte información de tus propios clientes."
                        ),
                    }
                else:
                    return {
                        "error": "CLIENTE_NO_ENCONTRADO",
                        "mensaje": (
                            f"No se encontró ningún cliente con el término '{ruc}' en tu cartera. "
                            "Por favor, pídele al usuario que verifique el nombre o te proporcione su RUC."
                        ),
                    }

        if ruc and ruc not in await _rucs_de_cartera(perfil):
            return {
                "error": "ACCESO_DENEGADO",
                "mensaje": (
                    "Ese cliente no pertenece a tu cartera asignada. "
                    "Solo puedo darte información de tus propios clientes."
                ),
            }

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

    # --- Fallback para búsqueda de productos si el SKU no es válido ---
    if name in ("consultar_stock", "consultar_precio") and isinstance(resultado, dict):
        if "error" in resultado or resultado.get("detail") == "Producto no encontrado":
            sku_query = args.get("sku_code", "").strip()
            if sku_query:
                try:
                    search_res = await sap.get_catalogo(q=sku_query)
                    productos = search_res.get("productos", []) if isinstance(search_res, dict) else []
                except Exception:
                    productos = []
                
                if productos:
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
                        ]
                    }

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
