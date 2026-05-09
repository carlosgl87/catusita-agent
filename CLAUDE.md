# CLAUDE.md — Agente IA Catusita

## Descripción del proyecto

Sistema multi-agente de IA para Grupo Catusita (distribuidora de repuestos automotrices).
Dos agentes de WhatsApp independientes sobre la misma infraestructura:
- **Agente Vendedores**: asesores comerciales internos con acceso completo (precios netos, crédito, cobranzas)
- **Agente Clientes**: talleres, distribuidores y consumidor final con acceso a información pública

Canal de comunicación: **WhatsApp vía Evolution API**
Backend: **FastAPI + Python**
LLM: **Claude API (claude-sonnet-4-20250514)**
Base de datos: **PostgreSQL + pgvector**
Sesiones: **Redis**

---

## Stack tecnológico

```
pip install fastapi uvicorn anthropic asyncpg redis pgvector httpx python-dotenv pydantic
```

---

## Estructura de carpetas a crear

```
catusita-agent/
├── CLAUDE.md                  ← este archivo
├── .env                       ← variables de entorno (nunca subir a git)
├── .env.example
├── .gitignore
├── requirements.txt
├── main.py                    ← entrada de FastAPI
│
├── orchestrator/
│   ├── __init__.py
│   ├── router.py              ← detecta intención y llama al agente correcto
│   ├── context.py             ← manejo de sesiones con Redis
│   └── profile.py             ← carga y valida el perfil del usuario
│
├── agents/
│   ├── __init__.py
│   ├── stock.py               ← consulta stock en SAP
│   ├── prices.py              ← precios netos, lista y escala de volumen
│   ├── orders.py              ← estado de pedidos y despacho
│   ├── credit.py              ← crédito y cartera (solo vendedores)
│   ├── documents.py           ← facturas, guías, notas de crédito
│   ├── catalog_rag.py         ← búsqueda semántica en catálogo de productos
│   ├── vehicle.py             ← identificación por placa/VIN
│   ├── collections.py         ← cobranzas y letras por vencer
│   └── claims.py              ← reclamos y devoluciones (clientes)
│
├── shared/
│   ├── __init__.py
│   ├── sap_client.py          ← cliente único para todas las APIs SAP (mock en dev)
│   ├── auth.py                ← autenticación por número WA, RUC o pedido
│   ├── llm.py                 ← wrapper de Claude API
│   ├── evolution.py           ← cliente de Evolution API para enviar mensajes
│   └── email_client.py        ← envío de correos para derivaciones
│
├── webhooks/
│   ├── __init__.py
│   └── whatsapp.py            ← recibe eventos de Evolution API
│
├── db/
│   ├── __init__.py
│   ├── connection.py          ← pool de conexiones PostgreSQL
│   ├── models.py              ← tablas: users, conversations, messages, claims
│   └── migrations/
│       └── 001_initial.sql
│
└── dashboard/                 ← React app (crear aparte, solo el backend por ahora)
```

---

## Variables de entorno (.env)

```env
# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# Evolution API (WhatsApp)
EVOLUTION_API_URL=https://evolution-api.up.railway.app
EVOLUTION_API_KEY=catusita-secret-key-2024
EVOLUTION_INSTANCE_VENDEDORES=catusita-vendedores
EVOLUTION_INSTANCE_CLIENTES=catusita-clientes

# PostgreSQL
DATABASE_URL=postgresql://user:password@host:5432/catusita_db

# Redis
REDIS_URL=redis://localhost:6379

# SAP (en dev usar mock, en prod la URL real)
SAP_API_URL=https://sap.catusita.com/api
SAP_API_KEY=...
USE_SAP_MOCK=true   # cambiar a false en producción

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=agente@catusita.com
SMTP_PASSWORD=...

# API Placa/VIN externa
PLACA_API_URL=https://api.vehiculos.pe
PLACA_API_KEY=...
```

---

## Paso 1 — Base de datos

Crear en `db/migrations/001_initial.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Usuarios autenticados
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('asesor', 'cliente')),
    whatsapp_number VARCHAR(20) UNIQUE,  -- para asesores
    ruc VARCHAR(20) UNIQUE,              -- para clientes
    nombre VARCHAR(100),
    linea_asignada VARCHAR(50),          -- solo asesores
    nivel_acceso VARCHAR(20) DEFAULT 'basico',
    activo BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Conversaciones
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    canal VARCHAR(20) DEFAULT 'whatsapp',
    agente_tipo VARCHAR(20) NOT NULL CHECK (agente_tipo IN ('vendedor', 'cliente')),
    numero_whatsapp VARCHAR(20),
    iniciada_at TIMESTAMP DEFAULT NOW(),
    ultima_actividad TIMESTAMP DEFAULT NOW(),
    activa BOOLEAN DEFAULT true
);

-- Mensajes
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    rol VARCHAR(15) NOT NULL CHECK (rol IN ('user', 'assistant', 'tool')),
    contenido TEXT NOT NULL,
    tool_name VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Reclamos registrados por el agente de clientes
CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_reclamo VARCHAR(20) UNIQUE NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    pedido_id VARCHAR(50),
    motivo TEXT,
    estado VARCHAR(20) DEFAULT 'pendiente',
    asesor_notificado BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Base de conocimiento vectorizada (RAG)
CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo VARCHAR(30),  -- 'catalogo', 'ficha_tecnica', 'equivalencia'
    titulo TEXT,
    contenido TEXT,
    metadata JSONB,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON knowledge_base USING ivfflat (embedding vector_cosine_ops);
```

---

## Paso 2 — Autenticación (`shared/auth.py`)

```python
# Lógica de autenticación:
# - Asesores: se identifican por su número de WhatsApp registrado en la tabla users
# - Clientes: se identifican con RUC o número de pedido en el primer mensaje
#
# La función get_or_create_user recibe el número de WhatsApp y el tipo de agente,
# busca en la BD y devuelve el perfil completo.
#
# Si el usuario no está registrado:
#   - Asesor: responder "Tu número no está registrado. Contacta a tu supervisor."
#   - Cliente: iniciar flujo de identificación (pedir RUC o N° de pedido)
#
# Estructura del perfil que devuelve:
# {
#   "user_id": "uuid",
#   "tipo": "asesor" | "cliente",
#   "nombre": "Luis García",
#   "linea_asignada": "filtros",     # solo asesores
#   "nivel_acceso": "completo",
#   "autenticado": True
# }
```

---

## Paso 3 — Cliente SAP con mock (`shared/sap_client.py`)

Implementar un cliente SAP con **dos modos**:
- `USE_SAP_MOCK=true` → devuelve datos simulados realistas para desarrollo
- `USE_SAP_MOCK=false` → llama a la API real de SAP

Implementar estos métodos:

```python
class SAPClient:
    async def get_stock(self, sku_code: str, almacen_id: int = 0) -> dict:
        # Retorna: {sku_code, almacen_1, almacen_2, total, bajo_stock}

    async def get_prices(self, sku_code: str, tipo_cliente: str,
                         asesor_id: str, cantidad: int = 1, zona: str = None) -> dict:
        # Retorna: {precio_lista, precio_neto, descuento_pct, escala_volumenes, precio_zona}

    async def get_order_status(self, pedido_id: str = None, ruc_cliente: str = None) -> dict:
        # Retorna: {pedido_id, estado, almacen_salida, guia_numero, hora_salida, entrega_estimada}

    async def get_credit(self, cliente_id: str, meses_historial: int = 18) -> dict:
        # Retorna: {limite_credito, deuda_actual, disponible, maximo_18_meses,
        #           letras_pendientes, calificacion_pago}

    async def get_documents(self, cliente_id: str, pedido_id: str = None,
                            tipo_doc: str = "todos", formato: str = "pdf") -> dict:
        # Retorna: {documentos: [{tipo, numero, fecha, monto, estado_pago, url_pdf, url_xml}]}

    async def get_restock_date(self, sku_code: str) -> dict:
        # Retorna: {sku_code, stock_actual, lotes_en_transito}

    async def get_stock_aging(self, almacen_id: int = 0, dias_minimos: int = 90) -> dict:
        # Retorna: {items: [{sku_code, descripcion, almacen, cantidad, dias_en_almacen}]}

    async def get_collections_report(self, asesor_id: str, semana: str = None) -> dict:
        # Retorna: {total_por_cobrar, vencido, al_dia, letras: [{cliente, monto, fecha_vcto}]}
```

Para el mock, usar datos realistas de repuestos automotrices peruanos.

---

## Paso 4 — Los agentes especializados

Cada agente en `agents/` recibe los argumentos que Claude extrae del mensaje
y llama a `SAPClient` o al RAG. Devuelve siempre un dict con la respuesta.

### `agents/stock.py`
```python
async def consultar_stock(sku_code: str, almacen_id: int = 0) -> dict:
    # Llama a sap_client.get_stock()
    # Formatea la respuesta con nombres de almacén (1=Miraflores, 2=Ate)

async def consultar_reposicion(sku_code: str) -> dict:
    # Llama a sap_client.get_restock_date()

async def consultar_antiguedad(almacen_id: int = 0, dias_minimos: int = 90) -> dict:
    # Llama a sap_client.get_stock_aging()
```

### `agents/prices.py`
```python
async def consultar_precio(sku_code: str, tipo_cliente: str,
                            asesor_id: str, cantidad: int = 1, zona: str = None) -> dict:
    # Llama a sap_client.get_prices()
    # Incluye escala de descuentos por volumen en la respuesta
```

### `agents/orders.py`
```python
async def consultar_pedido(pedido_id: str = None, ruc_cliente: str = None) -> dict:
    # Llama a sap_client.get_order_status()

async def consultar_almacen_producto(sku_code: str) -> dict:
    # Llama a sap_client.get_stock() y formatea para respuesta de cliente
```

### `agents/credit.py`
```python
async def consultar_credito(cliente_id: str) -> dict:
    # Llama a sap_client.get_credit()
    # SOLO disponible para asesores (verificar en el orquestador antes de llamar)
```

### `agents/documents.py`
```python
async def obtener_documentos(cliente_id: str, pedido_id: str = None,
                              tipo_doc: str = "todos", formato: str = "pdf") -> dict:
    # Llama a sap_client.get_documents()
    # Retorna URLs de descarga de PDF/XML
```

### `agents/catalog_rag.py`
```python
async def buscar_catalogo(query: str, placa: str = None, vin: str = None) -> dict:
    # 1. Si hay placa/VIN, primero identificar el vehículo
    # 2. Generar embedding de la query con Claude o text-embedding-3-small de OpenAI
    # 3. Buscar en pgvector con similaridad coseno
    # 4. Devolver los top 3-5 resultados más relevantes

async def obtener_equivalencias(sku_code: str = None, codigo_oem: str = None) -> dict:
    # Busca en la base de conocimiento equivalencias entre marcas
    # Devuelve lista de alternativas con stock disponible

async def obtener_ficha_tecnica(sku_code: str) -> dict:
    # Devuelve la ficha técnica del producto (PDF adjunto + especificaciones clave)
```

### `agents/vehicle.py`
```python
async def identificar_vehiculo(placa: str = None, vin: str = None) -> dict:
    # Llama a la API externa de placas/VIN
    # Retorna: {marca, modelo, anio, motor, combustible, vin}
```

### `agents/collections.py`
```python
async def consultar_letras_proximas(asesor_id: str, dias: int = 7) -> dict:
    # Llama a sap_client y filtra letras por vencer en los próximos N días
    # SOLO para asesores

async def reporte_cobranzas(asesor_id: str, semana: str = None) -> dict:
    # Devuelve el reporte de cobranzas de la cartera del asesor
    # SOLO para asesores
```

### `agents/claims.py`
```python
async def registrar_reclamo(conversation_id: str, pedido_id: str, motivo: str) -> dict:
    # Genera número de reclamo (REC-XXXX)
    # Guarda en la tabla claims
    # Notifica al asesor asignado por WhatsApp y email
    # SOLO para clientes
```

---

## Paso 5 — El Orquestador (`orchestrator/router.py`)

Este es el núcleo del sistema. Implementar el loop de tool use de Claude:

```python
# TOOLS para el AGENTE VENDEDORES (acceso completo)
TOOLS_VENDEDORES = [
    {
        "name": "consultar_stock",
        "description": "Consulta el stock disponible de un producto en los almacenes. Usar cuando pregunten por disponibilidad, inventario o si hay un producto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string", "description": "Código SKU del producto"},
                "almacen_id": {"type": "integer", "description": "0=ambos, 1=Miraflores, 2=Ate"}
            },
            "required": ["sku_code"]
        }
    },
    {
        "name": "consultar_precio",
        "description": "Consulta el precio neto según tipo de cliente y escala de descuentos por volumen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_code": {"type": "string"},
                "tipo_cliente": {"type": "string", "enum": ["tienda", "taller", "consumidor"]},
                "cantidad": {"type": "integer", "description": "Cantidad a comprar para calcular descuento por volumen"},
                "zona": {"type": "string", "description": "Zona geográfica del cliente (opcional)"}
            },
            "required": ["sku_code", "tipo_cliente"]
        }
    },
    {
        "name": "consultar_pedido",
        "description": "Consulta el estado y ubicación de un pedido en tiempo real.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pedido_id": {"type": "string"},
                "ruc_cliente": {"type": "string", "description": "Alternativo al pedido_id"}
            }
        }
    },
    {
        "name": "consultar_credito",
        "description": "Consulta el límite de crédito, saldo disponible, deuda actual e historial de letras de un cliente. Solo disponible para asesores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {"type": "string", "description": "RUC o código SAP del cliente"}
            },
            "required": ["cliente_id"]
        }
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
                "formato": {"type": "string", "enum": ["pdf", "xml", "ambos"]}
            },
            "required": ["cliente_id"]
        }
    },
    {
        "name": "buscar_catalogo",
        "description": "Busca productos en el catálogo por descripción, síntoma o compatibilidad. Usar para equivalencias, fichas técnicas y búsqueda semántica.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Búsqueda en lenguaje natural"},
                "placa": {"type": "string", "description": "Placa del vehículo (opcional)"},
                "vin": {"type": "string", "description": "VIN/Chasis del vehículo (opcional)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "identificar_vehiculo",
        "description": "Identifica la marca, modelo y año de un vehículo a partir de su placa o VIN para filtrar repuestos compatibles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "placa": {"type": "string"},
                "vin": {"type": "string"}
            }
        }
    },
    {
        "name": "consultar_letras_proximas",
        "description": "Muestra qué clientes de la cartera del asesor tienen letras por vencer en los próximos días.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {"type": "integer", "description": "Días hacia adelante a revisar (default: 7)"}
            }
        }
    },
    {
        "name": "reporte_cobranzas",
        "description": "Genera el reporte de cobranzas de la cartera del asesor para una semana.",
        "input_schema": {
            "type": "object",
            "properties": {
                "semana": {"type": "string", "description": "Semana a consultar en formato 'YYYY-WNN' (opcional, default: semana actual)"}
            }
        }
    },
    {
        "name": "consultar_antiguedad_stock",
        "description": "Muestra qué productos llevan más días en almacén para priorizar su venta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dias_minimos": {"type": "integer", "description": "Filtro de días mínimos en almacén (default: 90)"},
                "almacen_id": {"type": "integer", "description": "0=ambos, 1=Miraflores, 2=Ate"}
            }
        }
    }
]

# TOOLS para el AGENTE CLIENTES (solo información pública)
# Incluir solo: consultar_stock (precio lista solamente), consultar_pedido,
# obtener_documentos (propios), buscar_catalogo, identificar_vehiculo, registrar_reclamo
# NO incluir: consultar_credito, consultar_precio (neto), reporte_cobranzas,
#             consultar_letras, consultar_antiguedad_stock
TOOLS_CLIENTES = [...]  # definir con el subconjunto correcto

# SYSTEM PROMPTS
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
- Para reclamos, registra el reclamo y confirma el número de caso
- Nunca inventes información — siempre usa las tools disponibles"""

# LOOP PRINCIPAL
async def run_agent(mensaje: str, perfil: dict, historial: list) -> str:
    """
    Ejecuta el loop de tool use de Claude hasta obtener una respuesta final.

    Args:
        mensaje: mensaje del usuario
        perfil: {user_id, tipo, nombre, linea_asignada, nivel_acceso}
        historial: lista de mensajes previos de la conversación (últimos 10)

    Returns:
        respuesta final como string para enviar por WhatsApp
    """
    tools = TOOLS_VENDEDORES if perfil["tipo"] == "asesor" else TOOLS_CLIENTES
    system = SYSTEM_VENDEDOR.format(**perfil) if perfil["tipo"] == "asesor" else SYSTEM_CLIENTE

    messages = historial + [{"role": "user", "content": mensaje}]

    while True:
        response = await llm.create_message(
            system=system,
            tools=tools,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            return next(b.text for b in response.content if hasattr(b, "text"))

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    resultado = await execute_tool(block.name, block.input, perfil)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(resultado, ensure_ascii=False)
                    })

            messages.append({"role": "user", "content": tool_results})
```

La función `execute_tool` mapea el nombre de la tool a la función del agente correcto
y pasa el `perfil` para verificar permisos antes de ejecutar.

---

## Paso 6 — Manejo de contexto (`orchestrator/context.py`)

```python
# Usar Redis para almacenar el historial de conversación
# Key: f"conversation:{numero_whatsapp}"
# Value: JSON con los últimos 10 mensajes (para no exceder el context window)
# TTL: 2 horas de inactividad

async def get_history(numero: str) -> list:
    # Obtiene el historial de Redis
    # Si no existe, devuelve []

async def save_message(numero: str, rol: str, contenido: str):
    # Agrega el mensaje al historial
    # Mantiene solo los últimos 10 mensajes
    # Renueva el TTL a 2 horas

async def clear_history(numero: str):
    # Limpia la conversación (comando "reiniciar" del usuario)
```

---

## Paso 7 — Webhook de WhatsApp (`webhooks/whatsapp.py`)

```python
@router.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    """
    Recibe todos los eventos de Evolution API.
    Filtrar solo MESSAGES_UPSERT y mensajes de texto entrantes.
    """
    data = await request.json()

    # 1. Ignorar mensajes enviados por nosotros (fromMe: true)
    if data.get("data", {}).get("key", {}).get("fromMe"):
        return {"status": "ignored"}

    # 2. Extraer número y texto del mensaje
    # El texto puede estar en data.message.conversation
    # o en data.message.extendedTextMessage.text
    numero = data["data"]["key"]["remoteJid"].replace("@s.whatsapp.net", "")
    texto = (data["data"].get("message", {}).get("conversation") or
             data["data"].get("message", {}).get("extendedTextMessage", {}).get("text"))

    if not texto:
        return {"status": "ignored"}  # ignorar imágenes/audios/stickers en v1

    # 3. Determinar qué agente recibió el mensaje (por el nombre de instancia)
    instance_name = data.get("instance", "")
    agente_tipo = "vendedor" if "vendedores" in instance_name else "cliente"

    # 4. Autenticar al usuario
    perfil = await auth.get_user_profile(numero, agente_tipo)
    if not perfil["autenticado"]:
        await evolution.send_message(numero, instance_name,
            "Para continuar necesito verificar tu identidad. Por favor, ingresa tu RUC o número de pedido.")
        return {"status": "auth_required"}

    # 5. Cargar historial de Redis
    historial = await context.get_history(numero)

    # 6. Ejecutar el orquestador
    respuesta = await router.run_agent(texto, perfil, historial)

    # 7. Guardar mensajes en Redis y en PostgreSQL
    await context.save_message(numero, "user", texto)
    await context.save_message(numero, "assistant", respuesta)

    # 8. Enviar respuesta por WhatsApp
    await evolution.send_message(numero, instance_name, respuesta)

    return {"status": "ok"}
```

---

## Paso 8 — Cliente de Evolution API (`shared/evolution.py`)

```python
class EvolutionClient:
    async def send_message(self, numero: str, instance: str, texto: str) -> dict:
        """
        POST {EVOLUTION_API_URL}/message/sendText/{instance}
        Headers: { apikey: EVOLUTION_API_KEY }
        Body: { number: "51{numero}", text: "{texto}" }
        """

    async def send_document(self, numero: str, instance: str,
                             url: str, filename: str, caption: str = "") -> dict:
        """
        Para enviar PDFs y XMLs adjuntos
        POST {EVOLUTION_API_URL}/message/sendMedia/{instance}
        """
```

---

## Paso 9 — main.py

```python
from fastapi import FastAPI
from webhooks.whatsapp import router as whatsapp_router
from db.connection import init_db

app = FastAPI(title="Catusita Agent API")

@app.on_event("startup")
async def startup():
    await init_db()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "catusita-agent"}

app.include_router(whatsapp_router, prefix="/webhook")
```

---

## Orden de construcción recomendado

Construir en este orden para poder probar en cada paso:

1. `db/` → crear tablas y pool de conexiones
2. `shared/sap_client.py` → implementar el mock completo con datos realistas
3. `agents/stock.py` y `agents/prices.py` → los más simples
4. `shared/llm.py` y `orchestrator/router.py` → el loop principal con solo stock y precios
5. Probar el orquestador desde la terminal (sin WhatsApp todavía)
6. `shared/evolution.py` → cliente de Evolution API
7. `webhooks/whatsapp.py` → conectar con Evolution API y probar en WhatsApp real
8. `shared/auth.py` y `orchestrator/context.py` → autenticación e historial
9. Resto de agentes: `orders.py`, `credit.py`, `documents.py`, `catalog_rag.py`, `vehicle.py`, `collections.py`, `claims.py`

---

## Funcionalidades completas del Agente Vendedores

### Situación crediticia
- Consulta de crédito disponible (límite, saldo, deuda, estado, última compra)

### Estado de pedidos y despacho
- Estado y ubicación de pedido en tiempo real
- En qué almacén está el producto (Miraflores o Ate)
- Fecha estimada de reposición de producto agotado
- Estado de factura y fecha de entrega
- Antigüedad de mercadería en almacén (+90 días)

### Precios y descuentos
- Precio neto según tipo de cliente (tienda / taller / consumidor final)
- Escala de precios por volumen (1-9, 10-24, 25-49, 50+ unidades)
- Precio diferenciado por zona geográfica (Lima vs provincias)

### Productos, stock y equivalencias
- Consulta de stock disponible por SKU
- Equivalencias y cross-referencia por código OEM
- Búsqueda por placa o VIN → repuestos compatibles
- Fichas técnicas e imágenes de productos (PDF adjunto)

### Documentos
- Consulta y descarga de facturas (PDF)
- Guía de remisión (PDF y XML para SUNAT)
- Notas de crédito emitidas

### Cobranzas
- Clientes con letras próximas a vencer (esta semana)
- Reporte de cobranzas de cartera (semanal)

---

## Funcionalidades completas del Agente Clientes

### Diagnóstico técnico
- Diagnóstico por síntomas del vehículo → productos compatibles

### Catálogo y fichas técnicas
- Consulta de catálogo por producto o vehículo
- Fichas técnicas de productos (PDF adjunto)
- Imágenes de productos
- Equivalencias de productos entre marcas

### Precios y stock
- Stock y precio de lista en tiempo real (nunca precios netos)

### Estado de pedidos
- Estado del pedido propio (con RUC o N° de pedido)
- Estado de factura y fecha de entrega
- En qué almacén está el producto

### Documentos
- Descarga de factura y guía de remisión (PDF) de sus propios pedidos

### Reclamos y devoluciones
- Registro de queja o reclamo (genera N° de caso, notifica al asesor asignado)

---

## APIs SAP a mockear en desarrollo

| API | Método | Descripción |
|-----|--------|-------------|
| Stock en tiempo real | `get_stock(sku, almacen)` | Cantidad por almacén y bajo_stock flag |
| Precios netos y lista | `get_prices(sku, tipo_cliente, asesor_id, cantidad, zona)` | Precio + escala volumétrica |
| Estado de pedidos | `get_order_status(pedido_id, ruc)` | Estado, guía, entrega estimada |
| Cartera y crédito | `get_credit(cliente_id, meses=18)` | Límite, deuda, historial letras |
| Facturas, guías, NC | `get_documents(cliente_id, pedido_id, tipo, formato)` | URLs de descarga |
| Fechas de reposición | `get_restock_date(sku)` | Lotes en tránsito y fechas |
| Antigüedad mercadería | `get_stock_aging(almacen, dias_min)` | Productos con N+ días en almacén |
| Reporte cobranzas | `get_collections(asesor_id, semana)` | Vencido, al día, lista de letras |

---

## Notas importantes

- **Nunca** mezclar información de vendedores y clientes: si el número de WhatsApp está en la instancia de vendedores, usar `TOOLS_VENDEDORES`; si está en la de clientes, usar `TOOLS_CLIENTES`
- **Historial**: mantener los últimos 10 mensajes en Redis para no exceder el context window de Claude
- **Errores de SAP**: si la API SAP falla, responder "En este momento no puedo acceder a esa información. Inténtalo en unos minutos."
- **Mensajes no-texto**: en v1, ignorar silenciosamente imágenes, audios y stickers
- **URL de ngrok**: si se desarrolla localmente, la URL de ngrok cambia en cada reinicio — actualizarla en el webhook de Evolution API
- **El .env nunca se sube a git** — asegurarse de que esté en .gitignore
