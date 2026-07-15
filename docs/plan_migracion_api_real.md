# Plan de migración — Matar el Mock SAP, enchufar la API real de Catusita

> Fecha: 2026-07-09
> Decisión tomada: **eliminar el Mock SAP como fuente de datos de negocio.**
> Lo único que se conserva del mundo "mock" es el **registro de usuarios autenticados**
> (número de WhatsApp → vendedor), que ya vive en el agente (`shared/auth.py`, `_MOCK_ASESORES`),
> NO en el mock SAP. Las tools sin dato real se **apagan** — nada se rellena con mock.
> Leer primero: [`informe_actual.md`](informe_actual.md)

---

## 0. Objetivo y arquitectura destino

Desplegar `tools_agente_catusita` en Railway y que **reemplace al mock SAP** como fuente de
datos del agente. El agente solo cambia una env var (`SAP_BASE_URL`).

```
WhatsApp → webhook → AUTH (registro local: número→vendedor)  ← ÚNICO "mock" que queda
                        │
                        ▼
                     GRAFO → tools ──┬─ 5 reales  → tools_agente_catusita (Railway) → API Catusita
                                     ├─ 7 sin dato → APAGADAS (no aparecen, agente avisa)
                                     └─ 3 externas → SUNARP / Yahuar / reclamos DB (sin cambios)
```

**Regla de oro:** cero datos mock de negocio. Si la API real no lo tiene, la tool no existe.

---

## 1. Qué se conserva, qué se elimina

### ✅ Se conserva
| Cosa | Dónde | Por qué |
|---|---|---|
| Registro de asesores (número→vendedor) | `shared/auth.py` → `_MOCK_ASESORES` | La API real NO mapea WhatsApp→vendedor. Es indispensable. |
| SUNARP, Yahuar, reclamos (DB) | tal cual | No dependen del mock |

### ❌ Se elimina
| Cosa | Acción |
|---|---|
| Servidor Mock SAP (Railway) | Dejar de apuntarle (`SAP_BASE_URL` → repo nuevo). Se puede apagar después. |
| 7 tools sin dato real | Quitar de `TOOLS_VENDEDOR_LC`/`TOOLS_CLIENTE_LC` + limpiar prompts |
| `_MOCK_CLIENTES_RUC` (auth de cliente por RUC) | Reemplazar por consulta real `/clientes/{ruc}` (o dejar para fase 2) |

---

## 2. Contrato objetivo (capturado del mock en vivo, 2026-07-09)

El repo nuevo debe devolver **exactamente este shape** para ser drop-in. Junto a cada campo,
si la API real lo puede llenar o no:

### `GET /stock/{sku}`
```json
{"sku","nombre","stock","stock_minimo","disponible","alerta_stock_bajo","unidad"}
```
Real API (`/api/stock/filter?ItemCode=`): llena `sku←itemCode`, `nombre←itemName`,
`stock←parseFloat(stock)`, `unidad←inventoryUnitOfMeasure`. **No tiene** `stock_minimo` →
`disponible = stock>0`, `alerta_stock_bajo=false` (o omitir).

### `GET /precios/{sku}`  ← falta implementar en el repo nuevo
```json
{"sku","nombre","precio_lista","moneda"}
```
Real API (`/api/price/filter?ItemCode=`): `precio_lista←finalPrice`, `moneda←currency`.
**No devolver `precio_neto` ni `descuento`** (no existen en la real y no deben salir).

### `GET /catalogo?q=&marca=&con_stock=`
```json
{"total", "productos":[{"sku","nombre","categoria","marca","unidad","compatibilidad"}]}
```
Real API (`/api/article/filter`): `sku←itemCode`, `nombre←itemName`, `marca←brandName`,
`compatibilidad←foreignName` (string), `categoria←specialtyName`. `con_stock` cruza con
`/api/stock/filter`. **No tiene** `precio_lista`/`precio_neto`/`stock_minimo` por artículo.

### `GET /clientes/{ruc}`
```json
{"ruc","razon_social","direccion","distrito","tipo","estado", ...}
```
Real API (`/api/client/CustomerbyFilter?RUCClient=`): `ruc←rucClient`, `razon_social←nameClient`,
`direccion←address`, `distrito←locality`. **No tiene** `tipo`/`estado`/`limite_credito`.

### `GET /vendedor/{id}/clientes`
```json
{"vendedor_id","clientes":[{"ruc","razon_social","distrito","estado", ...}]}
```
Real API (`/api/client/CustomerbySeller?SellerId=`): `ruc←rucClient`, `razon_social←nameClient`,
`distrito←locality`. **No tiene** `tipo`/`limite_credito`/`saldo_pendiente`/`ultimo_pedido`.
⚠️ **Bloqueante:** confirmar mapeo `vendedor_id → SellerId` (hoy `SellerId=1` = bucket "Gerencia" que ve todo).

> El acceso por cartera (`access.py`) solo necesita `ruc` y `razon_social` → ✅ ambos mapean.
> `pre_resolver` (nombre→RUC) igual → ✅. No se rompen con estos shapes.

---

## 3. Tools que se apagan (sin dato real)

Quitar de los toolsets y de los system prompts:

`buscar_pedido_por_id`, `consultar_pedidos`, `consultar_credito`, `consultar_cobranzas`,
`consultar_historial`, `obtener_documentos`, `identificar_vehiculo`.

- El agente ya no las ofrece. Si el usuario pregunta por crédito/pedidos/cobranzas, el prompt
  debe indicarle que esa consulta no está disponible por ahora y derive al canal correspondiente.
- `access.py` → `RUC_SCOPED_TOOLS`: quedan solo `consultar_perfil_cliente` (y las demás se van).

---

## 4. Plan de ejecución (por fases)

### Fase A — `tools_agente_catusita` como drop-in del mock  *(repo nuevo, no toca producción)*
1. Normalizar las 4 respuestas actuales al shape §2 (mapear campos, castear `stock` string→num).
2. Implementar `GET /precios/{sku}` → `/api/price/filter`.
3. `CATUSITA_BASE_URL` como env var (hoy hardcode en `catusita_client.py:13`).
4. Mantener el contrato de error del mock (404 → `{"error": ...}`).
5. Tests de contrato: comparar salida normalizada vs. golden files del mock (los de §2).

### Fase B — Desplegar en Railway
1. Crear servicio Railway desde el repo (`Dockerfile` ya existe). Health `/health`.
2. Setear `CATUSITA_BASE_URL=http://api.catusita.com:8092`.
3. Anotar la URL pública resultante.

### Fase C — Agente: apagar tools + apuntar a la URL nueva
1. Quitar las 7 tools de `TOOLS_VENDEDOR_LC`/`TOOLS_CLIENTE_LC` (`lc_tools.py`).
2. Limpiar `RUC_SCOPED_TOOLS` (`access.py`) y menciones en prompts (`prompts.py`).
3. Cambiar env `SAP_BASE_URL` → URL del repo nuevo. (Rollback = revertir esta env var.)
4. Actualizar `vendedor_id` en `_MOCK_ASESORES` al `SellerId` real (cuando se confirme el mapeo).

### Fase D — Testing
1. QA existente (`QA/`, `Preguntas_respuestas_esperadas.md`) contra el nuevo `SAP_BASE_URL`.
2. Casos borde reales: SKU sin stock (`data:[]`), `stock` string 6 decimales, `email` null,
   catálogo sin `q`/`marca` (400).
3. End-to-end por WhatsApp (WAHA) con un vendedor: stock, catálogo, precio, cartera, perfil.
4. Verificar que las 7 tools apagadas ya no se ofrecen y el agente responde con la derivación.

---

## 5. Bloqueantes antes de go-live

| # | Bloqueante | Estado |
|---|---|---|
| 1 | Mapeo `vendedor_id → SellerId` real (si no, la cartera trae clientes equivocados) | ⛔ pendiente confirmar con Catusita |
| 2 | ¿La API real exigirá JWT? Hoy los GET responden sin token | ⚠️ vigilar (login bloqueado por Fortinet al probar) |
| 3 | `/precios/{sku}` implementado y normalizado | ⛔ pendiente (Fase A) |
| 4 | Repo nuevo desplegado + URL | ⛔ pendiente (Fase B) |

---

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| `SellerId ≠ vendedor_id` → cartera equivocada | No cerrar cartera hasta confirmar mapeo |
| API real empieza a pedir JWT | Implementar login en `catusita_client.py` + guardar token |
| Campos que el prompt menciona y ya no existen (crédito, neto) | Limpiar prompts en Fase C |
| HTTP plano Catusita (puerto 8092) | Tramo Railway↔Catusita es HTTP; agente↔Railway es HTTPS. Aceptar o pedir TLS |

---

## 7. Rollback

Todo el switch de datos es **una env var** (`SAP_BASE_URL`). Revertir al mock es instantáneo
mientras el servicio mock siga arriba. Recomendación: **no apagar el mock SAP hasta pasar Fase D**.
