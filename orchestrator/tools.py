"""Definición de las tools (schemas) que se exponen a Claude.

Separadas del orquestador: aquí vive solo la *configuración* de qué tools
existen y su contrato. La lógica de ejecución está en router.py.
"""

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
        "description": "Consulta oficial en SUNARP por placa peruana. Tarda 20-60s, avisa al usuario que estás consultando. El resultado trae los datos del vehículo EN TEXTO en el campo 'datos_vehiculo_texto' (marca, modelo, año, color, VIN/serie, motor, propietario, etc.), extraídos de la tarjeta de identificación vehicular. SIEMPRE que exista 'datos_vehiculo_texto', preséntale esos datos al usuario por escrito en tu respuesta. Además, la FOTO de la tarjeta se le envía automáticamente por WhatsApp (cuando 'tiene_imagen' es true, menciónale que también le llega la foto). Los datos registrales (oficina/partida) vienen en 'sedes' y 'mensaje'.",
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
        "description": "Consulta oficial en SUNARP por placa peruana. Tarda 20-60s, avisa al usuario que estás consultando. El resultado trae los datos del vehículo EN TEXTO en el campo 'datos_vehiculo_texto' (marca, modelo, año, color, VIN/serie, motor, propietario, etc.), extraídos de la tarjeta vehicular. SIEMPRE que exista 'datos_vehiculo_texto', preséntale esos datos al usuario por escrito en tu respuesta. Además, la FOTO de la tarjeta se le envía automáticamente por WhatsApp (cuando 'tiene_imagen' es true, menciónale que también le llega la foto).",
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
