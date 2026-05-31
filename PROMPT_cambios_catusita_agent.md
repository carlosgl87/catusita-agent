# Instrucciones para Claude Code — Refactorizar catusita-agent

## Contexto

Este proyecto ya existe y está funcionando. El objetivo es refactorizarlo para conectarlo a un servidor externo de APIs mock (Mock SAP Server) que ya está deployado en Railway en:

```
https://mock-sap-catusita-production.up.railway.app
```

El Mock SAP Server tiene estos 11 endpoints (todos requieren header `X-API-Key: catusita-mock-key-2024`):

```
GET /stock/{sku}
GET /precios/{sku}
GET /pedidos/{cliente_ruc}
GET /credito/{cliente_ruc}
GET /cobranzas/{cliente_ruc}
GET /documentos/{cliente_ruc}
GET /clientes/{ruc}
GET /historial/{cliente_ruc}
GET /vehiculo/{placa_o_vin}
GET /catalogo?q=...&categoria=...&marca=...&con_stock=true
GET /vendedor/{id}/clientes
```

---

## Archivos a modificar

### 1. `.env.example` — Actualizar variables de entorno

Reemplazar las variables SAP viejas por las nuevas:

**Eliminar:**
```
SAP_API_URL=https://sap.catusita.com/api
SAP_API_KEY=
USE_SAP_MOCK=true
PLACA_API_URL=https://api.vehiculos.pe
PLACA_API_KEY=
```

**Agregar:**
```
# Mock SAP Server (en dev) / SAP real (en prod) — solo cambiar la URL
SAP_BASE_URL=https://mock-sap-catusita-production.up.railway.app
SAP_API_KEY=catusita-mock-key-2024
```

---

### 2. `shared/sap_client.py` — Reemplazar completamente

Eliminar todo el mock interno (los diccionarios `_MOCK_PRODUCTS`, `_MOCK_STOCK`, `_MOCK_PRICES`, `_MOCK_ORDERS`, `_MOCK_CREDIT`, `_MOCK_DOCUMENTS`, `_MOCK_COLLECTIONS`, y todos los métodos `_mock_*`).

El nuevo `sap_client.py` debe ser un cliente HTTP limpio que siempre llama al servidor externo:

```python
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SAP_BASE_URL = os.getenv("SAP_BASE_URL", "https://mock-sap-catusita-production.up.railway.app")
SAP_API_KEY = os.getenv("SAP_API_KEY", "catusita-mock-key-2024")


class SAPClient:
    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url=SAP_BASE_URL,
            headers={"X-API-Key": SAP_API_KEY},
            timeout=10.0,
        )

    async def _get(self, path: str, params: dict = None) -> dict:
        """Helper para GET con manejo de errores uniforme."""
        try:
            resp = await self._http.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": f"No encontrado: {path}"}
            return {"error": f"Error del servidor SAP: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "No se pudo conectar al servidor SAP. Inténtalo en unos minutos."}

    async def get_stock(self, sku_code: str) -> dict:
        return await self._get(f"/stock/{sku_code}")

    async def get_precios(self, sku_code: str, tipo: str = None) -> dict:
        params = {"tipo": tipo} if tipo else None
        return await self._get(f"/precios/{sku_code}", params=params)

    async def get_pedidos(self, cliente_ruc: str, estado: str = None, limite: int = None) -> dict:
        params = {}
        if estado:
            params["estado"] = estado
        if limite:
            params["limite"] = limite
        return await self._get(f"/pedidos/{cliente_ruc}", params=params or None)

    async def get_credito(self, cliente_ruc: str) -> dict:
        return await self._get(f"/credito/{cliente_ruc}")

    async def get_cobranzas(self, cliente_ruc: str, estado: str = None) -> dict:
        params = {"estado": estado} if estado else None
        return await self._get(f"/cobranzas/{cliente_ruc}", params=params)

    async def get_documentos(self, cliente_ruc: str, tipo: str = None) -> dict:
        params = {"tipo": tipo} if tipo else None
        return await self._get(f"/documentos/{cliente_ruc}", params=params)

    async def get_cliente(self, ruc: str) -> dict:
        return await self._get(f"/clientes/{ruc}")

    async def get_historial(self, cliente_ruc: str, meses: int = None) -> dict:
        params = {"meses": meses} if meses else None
        return await self._get(f"/historial/{cliente_ruc}", params=params)

    async def get_vehiculo(self, placa_o_vin: str) -> dict:
        return await self._get(f"/vehiculo/{placa_o_vin}")

    async def get_catalogo(self, q: str = None, categoria: str = None,
                            marca: str = None, con_stock: bool = None) -> dict:
        params = {}
        if q:
            params["q"] = q
        if categoria:
            params["categoria"] = categoria
        if marca:
            params["marca"] = marca
        if con_stock is not None:
            params["con_stock"] = str(con_stock).lower()
        return await self._get("/catalogo", params=params or None)

    async def get_cartera_vendedor(self, vendedor_id: str,
                                    estado: str = None, tipo: str = None) -> dict:
        params = {}
        if estado:
            params["estado"] = estado
        if tipo:
            params["tipo"] = tipo
        return await self._get(f"/vendedor/{vendedor_id}/clientes", params=params or None)


sap = SAPClient()
```

---

### 3. `agents/stock.py` — Actualizar para nueva API

```python
from shared.sap_client import sap


async def consultar_stock(sku_code: str) -> dict:
    result = await sap.get_stock(sku_code)
    if "error" in result:
        return result
    return result


async def buscar_productos(q: str = None, categoria: str = None,
                            marca: str = None, solo_con_stock: bool = False) -> dict:
    return await sap.get_catalogo(q=q, categoria=categoria,
                                   marca=marca, con_stock=solo_con_stock if solo_con_stock else None)
```

Eliminar `consultar_reposicion` y `consultar_antiguedad` — esos métodos ya no tienen endpoint en el mock SAP externo.

---

### 4. `agents/prices.py` — Actualizar para nueva API

```python
from shared.sap_client import sap


async def consultar_precio(sku_code: str, tipo: str = None) -> dict:
    """
    tipo puede ser 'neto' (solo para vendedores) o 'lista' (para clientes).
    Si no se especifica, devuelve ambos precios.
    """
    return await sap.get_precios(sku_code, tipo=tipo)
```

---

### 5. `agents/orders.py` — Actualizar para nueva API

```python
from shared.sap_client import sap


async def consultar_pedidos(cliente_ruc: str, estado: str = None) -> dict:
    return await sap.get_pedidos(cliente_ruc, estado=estado)
```

Eliminar `consultar_almacen_producto` — ya no aplica con la nueva API.

---

### 6. `agents/credit.py` — Actualizar para nueva API

```python
from shared.sap_client import sap


async def consultar_credito(cliente_ruc: str) -> dict:
    return await sap.get_credito(cliente_ruc)


async def consultar_historial(cliente_ruc: str, meses: int = 18) -> dict:
    return await sap.get_historial(cliente_ruc, meses=meses)
```

---

### 7. `agents/collections.py` — Actualizar para nueva API

```python
from shared.sap_client import sap


async def consultar_cobranzas(cliente_ruc: str, estado: str = None) -> dict:
    """
    estado puede ser: 'pendiente', 'vencida', 'pagada'
    """
    return await sap.get_cobranzas(cliente_ruc, estado=estado)


async def consultar_letras_proximas(cliente_ruc: str) -> dict:
    """Obtiene letras pendientes y vencidas del cliente."""
    result = await sap.get_cobranzas(cliente_ruc)
    if "error" in result:
        return result
    letras = result.get("letras", [])
    proximas = [l for l in letras if l.get("estado") in ("pendiente", "vencida")]
    return {
        "cliente_ruc": cliente_ruc,
        "total_deuda": result.get("total_deuda", 0),
        "deuda_vencida": result.get("deuda_vencida", 0),
        "letras_activas": proximas,
    }
```

---

### 8. `agents/vehicle.py` — Simplificar, ahora usa el mock SAP

Reemplazar completamente por:

```python
from shared.sap_client import sap


async def identificar_vehiculo(placa_o_vin: str) -> dict:
    """
    Acepta placa (formato ABC-123) o VIN (17 caracteres).
    El mock SAP detecta automáticamente cuál es cuál.
    """
    if not placa_o_vin:
        return {"error": "Se requiere placa o VIN"}
    return await sap.get_vehiculo(placa_o_vin)
```

Eliminar el diccionario `_MOCK_VEHICLES` y toda la lógica de mock — ahora el mock SAP maneja esto.

---

### 9. `agents/catalog_rag.py` — Simplificar, ahora usa el mock SAP

Reemplazar completamente por:

```python
from shared.sap_client import sap


async def buscar_catalogo(query: str, placa: str = None, vin: str = None) -> dict:
    """
    Busca productos en el catálogo.
    Si se proporciona placa o VIN, primero identifica el vehículo
    y luego busca repuestos compatibles.
    """
    vehiculo = None

    if placa or vin:
        placa_o_vin = placa or vin
        vehiculo_result = await sap.get_vehiculo(placa_o_vin)
        if "error" not in vehiculo_result:
            vehiculo = vehiculo_result
            # Si hay repuestos_compatibles en la respuesta del vehículo, usarlos directamente
            if vehiculo_result.get("repuestos_compatibles"):
                return {
                    "query": query,
                    "vehiculo": vehiculo,
                    "resultados": vehiculo_result["repuestos_compatibles"],
                    "total": len(vehiculo_result["repuestos_compatibles"]),
                }

    # Búsqueda en catálogo por texto
    result = await sap.get_catalogo(q=query)
    return {
        "query": query,
        "vehiculo": vehiculo,
        "resultados": result.get("productos", []),
        "total": result.get("total", 0),
    }
```

Eliminar todas las importaciones de `_MOCK_PRODUCTS`, `_MOCK_STOCK`, `_MOCK_PRICES` — ya no existen en `sap_client.py`.

---

### 10. Agregar `agents/cartera.py` — Archivo nuevo

Crear este archivo nuevo:

```python
from shared.sap_client import sap


async def consultar_cartera(vendedor_id: str, estado: str = None, tipo: str = None) -> dict:
    """
    Devuelve la cartera de clientes asignada al vendedor.
    estado: 'activo', 'suspendido', 'bloqueado'
    tipo: 'taller', 'distribuidor', 'consumidor_final'
    """
    return await sap.get_cartera_vendedor(vendedor_id, estado=estado, tipo=tipo)


async def consultar_perfil_cliente(ruc: str) -> dict:
    """Devuelve el perfil completo de un cliente por RUC."""
    return await sap.get_cliente(ruc)
```

---

### 11. `orchestrator/router.py` — 4 cambios

#### Cambio A: Actualizar imports al inicio del archivo

Agregar `cartera` a los imports:
```python
from agents import stock, prices, orders, credit, documents, catalog_rag, vehicle, collections, claims, cartera
```

#### Cambio B: Actualizar TOOLS_VENDEDORES

Reemplazar la lista completa `TOOLS_VENDEDORES` por esta:

```python
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
        "description": "Lista todos los clientes asignados a este asesor con su estado, crédito y último pedido. Usar cuando el asesor pregunte por 'mis clientes', 'mi cartera' o quiera ver todos sus clientes.",
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
]
```

#### Cambio C: Actualizar TOOLS_CLIENTES

Reemplazar `TOOLS_CLIENTES` por esta versión (sin precios netos, sin cartera, sin crédito, sin cobranzas):

```python
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
```

#### Cambio D: Actualizar `execute_tool` y `SYSTEM_VENDEDOR`

Reemplazar la función `execute_tool` por esta versión actualizada:

```python
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
        "registrar_reclamo": lambda: claims.registrar_reclamo(
            conv_id, args["pedido_id"], args["motivo"]
        ),
    }

    fn = dispatch.get(name)
    if fn is None:
        return {"error": f"Tool desconocida: {name}"}
    return await fn()
```

Reemplazar `SYSTEM_VENDEDOR` por esta versión (agrega la regla de solo precio lista):

```python
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
- Si una consulta requiere múltiples tools, ejecútalas todas antes de responder
- Si la consulta excede tus permisos o no tienes información suficiente, deriva al área correspondiente

El asesor {nombre} tiene asignada la línea: {linea_asignada}
ID del vendedor: {vendedor_id}"""
```

Actualizar también la sección donde se formatea el `SYSTEM_VENDEDOR` en `run_agent`:

```python
system = (
    SYSTEM_VENDEDOR.format(
        nombre=perfil.get("nombre", "Asesor"),
        linea_asignada=perfil.get("linea_asignada", "general"),
        vendedor_id=perfil.get("vendedor_id", "V001"),
    )
    if es_asesor
    else SYSTEM_CLIENTE
)
```

---

### 12. `agents/documents.py` — Actualizar firma

Actualizar el archivo para usar `cliente_ruc` en vez de `cliente_id`:

```python
from shared.sap_client import sap


async def obtener_documentos(cliente_ruc: str, tipo: str = None) -> dict:
    return await sap.get_documentos(cliente_ruc, tipo=tipo)
```

---

### 13. `shared/auth.py` — Agregar `vendedor_id` al perfil mock

En `_MOCK_ASESORES`, agregar el campo `vendedor_id` a cada asesor para que el router pueda usarlo al llamar a `consultar_cartera`:

```python
_MOCK_ASESORES = {
    "51987654321": {
        "user_id": "asesor-001",
        "tipo": "asesor",
        "nombre": "Luis García",
        "linea_asignada": "filtros y lubricantes",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-001",
        "vendedor_id": "V001",   # ← ID que usa el Mock SAP Server
        "autenticado": True,
    },
    "51912345678": {
        "user_id": "asesor-002",
        "tipo": "asesor",
        "nombre": "María Torres",
        "linea_asignada": "frenos y suspensión",
        "nivel_acceso": "completo",
        "asesor_id": "ASE-002",
        "vendedor_id": "V002",   # ← ID que usa el Mock SAP Server
        "autenticado": True,
    },
}
```

---

## Verificación final

Después de hacer todos los cambios, verificar que:

1. No queden imports de `_MOCK_PRODUCTS`, `_MOCK_STOCK`, `_MOCK_PRICES` en ningún archivo (especialmente en `catalog_rag.py` que los importaba directamente)
2. No quede la variable `USE_SAP_MOCK` referenciada en ningún archivo
3. No queden métodos `_mock_*` en `sap_client.py`
4. El archivo `agents/cartera.py` fue creado
5. `agents/__init__.py` incluye `cartera` si es necesario

Luego probar con:
```bash
python test_terminal.py
```

Si `test_terminal.py` no tiene tests para los nuevos endpoints, agregar al menos uno que llame a `consultar_cartera` con `vendedor_id="V001"`.

---

## Notas importantes

- NO tocar `main.py`, `webhooks/whatsapp.py`, `orchestrator/context.py`, `db/`, ni `shared/evolution.py` — esos archivos están correctos y no necesitan cambios
- NO tocar `agents/claims.py` — está correcto
- El `shared/llm.py` tampoco cambia
- El objetivo es que después de estos cambios, el agente llame al Mock SAP Server externo en lugar de usar datos hardcodeados internos
