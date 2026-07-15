# Informe del estado actual — Agente Catusita (agente ↔ Mock SAP)

> Fecha: 2026-07-09
> Propósito: registrar **cómo funciona hoy todo el sistema** (agente + Mock SAP), para no
> perder contexto al migrar la fuente de datos a la API real de Catusita.
> Complementa (no reemplaza) `CLAUDE.md`. El plan de cambio está en
> [`plan_migracion_api_real.md`](plan_migracion_api_real.md).

---

## 1. Qué es hoy el sistema

Un asistente de WhatsApp para Grupo Catusita, con **dos canales** sobre la misma base de código:

- **Canal vendedor** (asesores): acceso completo — stock, precio, pedidos, crédito, cobranzas,
  documentos, cartera, catálogo, placa. 14 tools.
- **Canal cliente** (talleres/consumidor): solo información pública. 9 tools.

```
WhatsApp ─(WAHA)─► webhook ─► auth ─► historial(Redis) ─► GRAFO LangGraph ─► respuesta ─(WAHA)─► WhatsApp
                                                              │
                                                              └─► Mock SAP (datos)  ← ESTO se migra
```

- **Canal de mensajería:** WAHA (WhatsApp HTTP API, edición Core). Ver `instrucciones_waha.md`.
  (El código soporta también Kapso; se elige con `WHATSAPP_PROVIDER`.)
- **LLM:** Claude (`shared/llm.py`, modelo `claude-sonnet-4-6`).
- **Orquestación:** **LangGraph** (`USE_LANGGRAPH=true`). Fallback a router manual disponible.
- **Fuente de datos de negocio:** **Mock SAP** (`mock-sap-catusita-production.up.railway.app`),
  todo inventado. **Este es el único componente que la migración reemplaza.**

---

## 2. Flujo de un mensaje, de punta a punta

Archivo: `webhooks/whatsapp.py`.

1. **Webhook** recibe el evento de WAHA (batch). Ignora `fromMe`, filtra por tipo.
2. **Guardrail Yahuar**: si el mensaje viene del bot Yahuar (por número o LID), no entra al
   agente — se procesa como relay de placa (ver §7).
3. **Auth** (`shared/auth.py`): resuelve el número de WhatsApp a un perfil. En sandbox
   (`USE_AUTH_MOCK=true`) cualquier número entra como asesor **V001**.
4. **Historial** (`orchestrator/context.py`): lee de Redis los últimos mensajes de esa conversación.
5. **Grafo** (`orchestrator/graph.py` → `run_agent_graph_full`): procesa el mensaje y produce
   una respuesta de texto + `media_pendiente` (imágenes a enviar, ej. tarjeta de placa).
6. **Persistencia**: guarda user + assistant en Redis (y PostgreSQL si `DATABASE_URL`).
7. **Envío**: manda la respuesta por WAHA; si hay `media_pendiente`, manda también la(s) imagen(es).

`main.py` es un FastAPI mínimo: `/health` + el router del webhook bajo `/webhook`.

---

## 3. El grafo LangGraph (núcleo del agente)

Topología (`orchestrator/graph.py`):

```
START → pre_resolver → agente ──(hay tool_calls?)──► tools ──► agente
                           └──(no)──► validar ──(ok)──► END
                                         └──(falla, quedan intentos)──► agente
```

Estado compartido (`orchestrator/graph_state.py` → `AgentState`): `messages`, `perfil`,
`canal`, `media_pendiente`, `contexto_resuelto`, `validacion`, `intentos_validacion`.
`RECURSION_LIMIT=15` (env `LANGGRAPH_RECURSION_LIMIT`) corta cualquier loop.

### Nodo 1 — `pre_resolver` (sin LLM)
`orchestrator/nodes/pre_resolver.py`. Extrae entidades del mensaje por regex antes del LLM:
RUC, pedido (`PED-XXXX`), placa, SKU. Para asesores, además resuelve **nombre de cliente → RUC**
buscando en su cartera. El resultado va a `contexto_resuelto` y se inyecta al prompt para que
el agente no repregunte datos que el usuario ya dio.
> ⚠️ Depende del shape del mock: `consultar_cartera` → `data.get("clientes")`, `c["ruc"]`, `c["razon_social"]`.

### Nodo 2 — `agente` (LLM con tools)
`orchestrator/nodes/agente.py`. `ChatAnthropic.bind_tools()` con el toolset del canal
(vendedor/cliente) + el system prompt correspondiente (`orchestrator/prompts.py`). Decide qué
tools llamar. Si el validador rechazó una respuesta previa, recibe la nota de corrección aquí.

### Nodo 3 — `tools` (`ToolNode`)
Ejecuta las tools que el modelo pidió. Las tools están en `orchestrator/lc_tools.py` (ver §4).

### Nodo 4 — `validar` (reglas baratas + juez LLM)
`orchestrator/nodes/validar.py`. Revisa la respuesta antes de enviarla:
- **Regla 1 — privacidad**: bloquea revelar precio neto/descuento/almacén/ruta (solo canal vendedor).
- **Regla 2 — repregunta con contexto**: si `pre_resolver` ya resolvió el RUC/pedido y el agente
  igual lo pide → rechaza.
- **Regla 3 — no usó tools**: si la consulta requería datos y el agente pidió datos en vez de usar tools → rechaza.
- **Regla 4 — juez LLM**: solo si se usaron tools sensibles (`consultar_credito`,
  `consultar_cobranzas`, `consultar_perfil_cliente`) — audita privacidad/autorización falsa.
- `MAX_REINTENTOS=1`: tras un reintento fallido, deja pasar con warning (no loopea).

---

## 4. Tools del agente y su fuente de datos

`orchestrator/lc_tools.py`. Cada `@tool` recibe `perfil`/`tool_call_id` inyectados, aplica
control de acceso por cartera cuando corresponde, y devuelve `Command(update=...)`.

**14 tools canal vendedor / 9 canal cliente.** Fuente de datos:

### 4.1 Dependen del Mock SAP (se migran)
| Tool | Método `SAPClient` | Ruta del mock |
|---|---|---|
| `consultar_stock` | `get_stock` | `/stock/{sku}` |
| `consultar_precio` | `get_precios` | `/precios/{sku}` |
| `buscar_pedido_por_id` | `get_pedido_por_id` | `/pedido/{id}` |
| `consultar_pedidos` | `get_pedidos` | `/pedidos/{ruc}` |
| `consultar_credito` | `get_credito` | `/credito/{ruc}` |
| `consultar_cobranzas` | `get_cobranzas` | `/cobranzas/{ruc}` |
| `consultar_historial` | `get_historial` | `/historial/{ruc}` |
| `obtener_documentos` | `get_documentos` | `/documentos/{ruc}` |
| `consultar_cartera` | `get_cartera_vendedor` | `/vendedor/{id}/clientes` |
| `consultar_perfil_cliente` | `get_cliente` | `/clientes/{ruc}` |
| `buscar_catalogo` | `get_catalogo` + `get_vehiculo` | `/catalogo`, `/vehiculo/{placa}` |
| `identificar_vehiculo` | `get_vehiculo` | `/vehiculo/{placa}` |

### 4.2 NO dependen del Mock SAP (no se tocan en la migración)
| Tool | Fuente real |
|---|---|
| `consultar_placa_sunarp` | scraper SUNARP en vivo (ruta `/placas/{placa}`, 20-60s, devuelve foto) |
| `consultar_placa_yahuar` | relay WhatsApp al bot Yahuar (`shared/yahuar.py`) |
| `registrar_reclamo` | PostgreSQL propia (`db/models.py`, tabla `claims`) |

---

## 5. El Mock SAP (fuente de datos a reemplazar)

- Cliente único: `shared/sap_client.py` → `SAPClient` (httpx + header `X-API-Key`).
- Config: `SAP_BASE_URL` (default mock en Railway) y `SAP_API_KEY`.
- Manejo de errores uniforme en `_get()`: 404 → `{"error": ...}`, timeout/red → mensaje amable.
- **16 endpoints en total; el agente consume 13.** Devuelven el objeto de negocio directo
  (sin wrapper), con **claves en español** (`productos`, `total`, `sku`, `nombre`, `ruc`,
  `razon_social`, `clientes`, `repuestos_compatibles`, …).

Shapes representativos que el código ya asume:
```
/catalogo          → { productos: [{ sku, nombre, categoria, marca, ... }], total }
/vendedor/{id}/... → { clientes: [{ ruc, razon_social, tipo, estado, ... }] }
/clientes/{ruc}    → { ruc, razon_social, direccion, tipo, vendedor, estado, ... }
/stock/{sku}       → objeto de stock
/vehiculo/{placa}  → { repuestos_compatibles: [...] }
```

> Este acoplamiento (claves en español + estructura `{productos,total}` / `{clientes}`) es lo
> que hay que preservar o normalizar al migrar. Lo consumen: `agents/*.py`, `_sku_fallback`
> en `lc_tools.py`, `pre_resolver.py` y `access.py`.

---

## 6. Control de acceso, contexto y persistencia

- **Acceso por cartera** (`orchestrator/access.py`): un asesor solo consulta clientes de SU
  cartera. Tools RUC-scoped: crédito, cobranzas, historial, pedidos, documentos, perfil.
  Resuelve nombre parcial → RUC contra la cartera (del Mock SAP). Bloquea con `ACCESO_DENEGADO`
  si el RUC no es de su cartera.
- **Contexto** (`orchestrator/context.py`): historial de conversación en Redis por número,
  con TTL. Últimos N mensajes para no exceder el context window.
- **Persistencia** (`db/`): PostgreSQL opcional (`DATABASE_URL`). Guarda conversaciones,
  mensajes, reclamos y logs de uso de tools. En sandbox mock no se escribe (evita romper FKs).

---

## 7. Fuentes de datos que NO se tocan

- **SUNARP** (`sap.get_placa`): scraping oficial en vivo por placa. Devuelve datos + foto de la
  tarjeta vehicular. Latencia 20-60s. Tiene kill switch (`SUNARP_ENABLED=false`) que redirige a Yahuar.
- **Yahuar** (`shared/yahuar.py`): bot de WhatsApp externo (`51977504279`) que también da datos
  de placa. El agente le manda la placa y hace **relay** de su respuesta (texto + foto) al usuario,
  usando Redis para coordinar (pendiente, acumulador con debounce de 7s, aprendizaje de LID).
- **PostgreSQL propia**: reclamos y logs. No es SAP.

---

## 8. Despliegue y variables de entorno

- **Agente** (`catusita-agent`): Railway, deploy por `git push` a `main`
  (repo `carlosgl87/catusita-agent`). **No** usar `railway up --detach` (rompe `start.sh` por CRLF).
- **Mock SAP**: Railway (`mock-sap-catusita-production.up.railway.app`).
- **WAHA**: Railway, servicio aparte (ver `instrucciones_waha.md`).

Env vars clave:
```
# Datos (lo que se migra)
SAP_BASE_URL, SAP_API_KEY

# Canal y modo
WHATSAPP_PROVIDER=waha        USE_LANGGRAPH=true       USE_AUTH_MOCK=true
WAHA_BASE_URL, WAHA_API_KEY, WAHA_SESSION

# Comportamiento
SUNARP_ENABLED, YAHUAR_LID, LANGGRAPH_RECURSION_LIMIT
ANTHROPIC_API_KEY, REDIS_URL, DATABASE_URL (opcional)
PYTHONUNBUFFERED=1           # imprescindible para ver logs
```

---

## 9. Resumen: qué está en juego al migrar

1. **Un solo punto de red toca el SAP:** `shared/sap_client.py`. Cambiar `SAP_BASE_URL` es todo
   lo que necesita el agente si la fuente nueva respeta el mismo contrato.
2. **El agente está acoplado al shape del mock** (claves español, `{productos,total}`,
   `{clientes}`) en 4 lugares: `agents/*.py`, `_sku_fallback`, `pre_resolver.py`, `access.py`.
3. **SUNARP, Yahuar, Redis y la BD propia no cambian.**
4. El detalle de cobertura real vs. mock y las fases de cambio están en
   [`plan_migracion_api_real.md`](plan_migracion_api_real.md).
