# Qué falta para llegar al 100% (vs. lo que hacía con el mock)

> Fecha: 2026-07-10
> Contexto: el agente migró del Mock SAP (16 endpoints, data inventada, cubría el 100% del
> spec) a la API real de Catusita, que hoy solo alimenta **5 de esas capacidades**. Este
> documento lista TODO lo que quedó afuera y qué se necesita para recuperarlo.
> Relacionado: [`plan_migracion_api_real.md`](plan_migracion_api_real.md), [`informe_actual.md`](informe_actual.md).

---

## Resumen ejecutivo

| Estado | Capacidades |
|---|---|
| ✅ **Funciona con data real** (5) | Stock, precio de lista, catálogo, cartera de clientes, perfil de cliente |
| 🟡 **Funciona pero incompleto** | Cartera y perfil (faltan campos), catálogo (sin precio/stock por ítem), stock (sin mínimos/almacén) |
| 🔴 **Apagado — sin fuente real** (7) | Pedidos, crédito, cobranzas, historial, documentos, compatibilidad por placa/VIN, precio neto/descuentos |
| ⚙️ **Pendiente de infra/negocio** | Mapeo número→SellerId, auth de producción, placas SUNARP, posible JWT |

**Para el 100% se necesita, sobre todo, que Catusita exponga endpoints que hoy no existen.**
Es una dependencia externa, no de desarrollo del agente.

---

## 1. Capacidades apagadas — requieren NUEVOS endpoints de Catusita

Estas 7 tools se apagaron porque la API real de Catusita **no tiene de dónde sacar el dato**.
Para recuperarlas, Catusita debe exponer el endpoint correspondiente; recién ahí se reconecta
la tool (el código del agente ya existe, solo hay que reactivarlo y normalizar el shape).

| # | Capacidad | Qué hacía | Qué se necesita de Catusita |
|---|---|---|---|
| 1 | **Estado de pedidos** | Buscar pedido por N°, ver pedidos de un cliente, estado/seguimiento de despacho | Endpoint de pedidos/ventas (por N° de pedido y por RUC) con estado, fechas, guía |
| 2 | **Crédito** | Línea de crédito, deuda actual, disponible de un cliente | Endpoint de cuentas por cobrar / crédito por cliente |
| 3 | **Cobranzas** | Letras, facturas vencidas, vencimientos, reporte semanal por cartera | Endpoint de cobranzas / letras por cliente y por vendedor |
| 4 | **Historial de compras** | Compras de un cliente en los últimos N meses | Endpoint de historial de ventas por cliente |
| 5 | **Documentos** | Facturas, guías de remisión, notas de crédito (PDF/XML) | Endpoint de documentos electrónicos (con URLs de descarga) |
| 6 | **Compatibilidad por placa/VIN** | Repuestos del catálogo que calzan con un vehículo | Datos de aplicación/compatibilidad vehículo→repuesto (o cruce con el `foreignName` del catálogo) |
| 7 | **Precio neto / descuentos** | Precio neto, escala por volumen, precio por zona | La API de precios solo da **precio de lista** (`finalPrice`); falta neto, descuentos y escalas |

> Nota sobre el #7: por **política** el agente nunca debe revelar precio neto al usuario, así
> que esta brecha es más de completitud del dato que de funcionalidad de cara al vendedor.

---

## 2. Capacidades que funcionan pero INCOMPLETAS (faltan campos)

Las 5 tools activas responden, pero la API real trae **menos campos** que el mock. Esto limita
filtros y detalles que antes existían.

### 2.1 Cartera y perfil de cliente
La API real da: `ruc, razon_social, direccion, distrito, email, vendedor`.
**Faltan** (existían en el mock):
- `tipo` (taller / distribuidor / consumidor final) → **no se puede filtrar "mis distribuidores"**
- `estado` (activo / suspendido / bloqueado) → **no se puede filtrar "clientes activos"**
- `limite_credito`, `saldo_pendiente`, `ultimo_pedido` → sin resumen comercial del cliente

→ Para el 100%: Catusita debe incluir esos campos en el endpoint de clientes, o exponerlos aparte.

### 2.2 Catálogo
La API real da nombre, marca, categoría (`specialtyName`) y compatibilidad como **texto libre**.
**Faltan**: precio por producto en el listado, stock por producto en el listado,
`stock_minimo`, y `compatibilidad` estructurada (hoy es un string, no una lista de marcas/modelos).

### 2.3 Stock
La API real da `stock` (cantidad total) y unidad. **Faltan**:
- Desglose por **almacén/local** (el mock separaba Miraflores/Ate; la real trae `companyDefinition` IC/RJ pero sin significado de ubicación confirmado)
- `stock_minimo` y bandera de **stock bajo**

### 2.4 Otras del spec original nunca cubiertas por la real
- **Fecha de reposición / lotes en tránsito** de un producto agotado → falta endpoint de compras/inbound
- **Antigüedad de mercadería en almacén** (+90 días) → falta endpoint de inventario con fechas

---

## 3. Pendientes de infraestructura / negocio (no dependen de Catusita)

| Tema | Situación actual | Para el 100% |
|---|---|---|
| **Mapeo número WhatsApp → SellerId** | Todos los asesores de prueba comparten `SELLER_ID_DEMO=2` (Tarazona) | El negocio asigna a cada vendedor su `SellerId` real (ver [`vendedores_directorio.md`](vendedores_directorio.md)) y se carga en `shared/auth.py` |
| **Autenticación de producción** | Registro mock en código (`_MOCK_ASESORES`); sandbox mapea cualquier número a un asesor | Tabla real de asesores (número→vendedor) en base de datos, con `USE_AUTH_MOCK=false` |
| **Placas SUNARP** | El scraper vivía en el mock (`/placas`); tras el cutover ya no es alcanzable. Hoy las placas van por **Yahuar** (WhatsApp) | Reconectar SUNARP como servicio propio si se quiere la vía oficial, o mantener Yahuar como definitivo |
| **Login/JWT de Catusita** | Los GET responden sin token hoy | Si Catusita empieza a exigir JWT, implementar `POST /api/accounts/login` en el servicio intermedio (código previsto, no probado por firewall) |
| **Clientes por RUC (canal cliente)** | Auth de cliente por RUC sigue con `_MOCK_CLIENTES_RUC` | Conectar `/clientes/{ruc}` real para autenticar clientes por RUC |

---

## 4. Qué se necesita de cada parte para el 100%

**De Catusita (lo crítico y bloqueante):**
1. Endpoints de: pedidos, crédito, cobranzas, historial, documentos.
2. Campos faltantes en clientes: `tipo`, `estado`, crédito/saldo.
3. Precio y stock por producto en el catálogo; desglose de stock por almacén.
4. Datos de compatibilidad vehículo→repuesto (o confirmar que se puede derivar del catálogo).
5. Confirmar política de autenticación (JWT sí/no).

**Del negocio:**
1. Mapeo definitivo de cada número de WhatsApp a su `SellerId`.
2. Decidir si placas se quedan por Yahuar o se reconecta SUNARP.
3. Confirmar el significado de `companyDefinition` (IC/RJ) = ¿empresa? ¿almacén?

**De desarrollo (rápido, una vez llegue el dato):**
1. Reactivar cada tool apagada en `orchestrator/lc_tools.py` (ya están escritas).
2. Normalizar el nuevo endpoint al shape del mock en `tools_agente_catusita` (patrón ya establecido).
3. Devolver las menciones en los prompts (`orchestrator/prompts.py`).
4. Cargar el mapeo real de vendedores y pasar `USE_AUTH_MOCK=false`.

---

## 5. Priorización sugerida (mayor impacto comercial primero)

1. 🥇 **Mapeo número→SellerId** — sin esto la cartera no es de cada vendedor de verdad (ya desbloqueado técnicamente, falta el dato del negocio).
2. 🥈 **Campos de cliente (tipo/estado/crédito)** — habilita filtros de cartera y contexto comercial.
3. 🥉 **Pedidos + cobranzas** — lo que más piden los vendedores en el día a día.
4. **Documentos (facturas/guías)** — alto valor, depende de facturación electrónica.
5. **Historial de compras** — útil para seguimiento, menor urgencia.
6. **Compatibilidad por vehículo** — nice-to-have; hoy se suple buscando por nombre/marca.

---

## 6. Conclusión

El agente está **operativo y con datos reales** en su núcleo (stock, precio, catálogo, cartera,
clientes). El camino al 100% **no es más desarrollo del agente**, sino que **Catusita exponga los
endpoints faltantes** y el **negocio entregue el mapeo de vendedores**. En cuanto lleguen esos
datos, reactivar cada capacidad es un cambio chico y ya probado.
