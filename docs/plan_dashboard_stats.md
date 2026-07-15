# Plan — Dashboard de Estadísticas y Conversaciones (Catu)

> Fecha: 2026-07-14
> Base: los 2 mockups `catusita-estadisticas.png` y `catusita-conversaciones.png`.
> Objetivo: que TODA la data del dashboard se guarde automáticamente en la BD, en una
> tabla de hechos rica en dimensiones, para poder filtrar y ordenar por cualquier corte.
> Ya existe: front Vite `catu-panel`, API segura `/api/panel/*`, tabla `chat_messages`, login.

---

## 1. Qué piden los mockups

### Tab "Estadísticas" (con filtro por vendedor)
| Widget | Qué muestra |
|---|---|
| KPI Mensajes totales | total de mensajes |
| KPI Conversaciones | total de conversaciones (sesiones) |
| Evolución del uso | mensajes por semana desde el lanzamiento (línea) |
| Días de mayor uso | mensajes por día de semana (Lun–Dom) |
| Horas de mayor uso | mensajes por hora del día (7–18) |
| Tools más usadas | conteo y % por tool (Stock, Precio, Cliente, Cotización, Historial…) |
| Ranking de vendedores | mensajes por vendedor (ordenado) |
| Sin uso | vendedores que nunca escribieron |

### Tab "Conversaciones"
- Buscador (vendedor o número)
- Lista de conversaciones con última hora ("15:42", "Ayer")
- Visor de chat (burbujas, hora por mensaje)
- Encabezado: nombre del vendedor · N° mensajes · canal (`agente_ventas`)

---

## 2. Estado actual vs. lo que se necesita

Hoy guardamos en `chat_messages(id, numero, rol, contenido, created_at)`. Eso alcanza para el
visor de conversaciones, pero **NO** para las estadísticas con filtros. Gap por métrica:

| Métrica | Dato que necesita | ¿Está hoy? | Qué falta |
|---|---|---|---|
| Mensajes totales | count de mensajes | ✅ | (filtro por vendedor → falta vendedor en la fila) |
| Conversaciones | id de sesión | ❌ | definir "conversación" y asignar `session_id` |
| Evolución semanal | `created_at` | ✅ | ok |
| Días de mayor uso | día de semana de `created_at` | ⚠️ | **timezone** (hoy UTC, hay que pasar a America/Lima) |
| Horas de mayor uso | hora de `created_at` | ⚠️ | **timezone** America/Lima |
| Tools más usadas | qué tool disparó cada turno | ❌ | **no se registra ninguna tool** (mock salta el log) |
| Ranking de vendedores | vendedor por mensaje | ❌ | **falta vendedor_id/nombre en la fila** |
| Sin uso | roster completo de vendedores | ❌ | **falta la lista maestra de vendedores** en BD |

**Conclusión:** faltan 4 cosas → (a) identidad del vendedor y canal por mensaje, (b) registro
de tools usadas, (c) noción de sesión/conversación, (d) roster de vendedores. Más el manejo
de zona horaria.

---

## 3. Diseño de datos — la "tabla completa" (fuente única)

En vez de pre-agregar, se usa una **tabla de hechos** (un registro por mensaje) con todas las
dimensiones denormalizadas. Todos los widgets salen de `GROUP BY` + `WHERE` sobre esta tabla,
así cualquier filtro futuro (vendedor, fecha, canal, tool) funciona sin rehacer nada.

### Tabla `interaction_events` (reemplaza/expande `chat_messages`)
```sql
CREATE TABLE interaction_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- UTC; se convierte a Lima al consultar
    numero        VARCHAR(40) NOT NULL,                 -- teléfono resuelto (hilo)
    vendedor_id   VARCHAR(20),                          -- SellerId (ej. "28")
    vendedor_nombre VARCHAR(120),                       -- ej. "Osorio Echevarria..."
    canal         VARCHAR(20)  DEFAULT 'vendedor',      -- vendedor | cliente
    session_id    UUID,                                 -- agrupa la "conversación"
    rol           VARCHAR(15)  NOT NULL,                -- user | assistant
    tipo          VARCHAR(20)  DEFAULT 'texto',         -- texto | placa | imagen | sistema
    contenido     TEXT,                                 -- para el visor
    tools         TEXT[]       DEFAULT '{}',            -- tools usadas en ese turno
    latencia_ms   INTEGER,                              -- opcional (tiempo de respuesta)
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX idx_ev_ts        ON interaction_events (ts);
CREATE INDEX idx_ev_vendedor  ON interaction_events (vendedor_id, ts);
CREATE INDEX idx_ev_numero    ON interaction_events (numero, ts);
CREATE INDEX idx_ev_session   ON interaction_events (session_id);
CREATE INDEX idx_ev_tools     ON interaction_events USING GIN (tools);
```

### Tabla `vendedores` (roster maestro — para "Sin uso" y el filtro)
```sql
CREATE TABLE vendedores (
    vendedor_id   VARCHAR(20) PRIMARY KEY,   -- SellerId
    codigo        VARCHAR(20),               -- codeSeller (0051, ...)
    nombre        VARCHAR(120),
    whatsapp      VARCHAR(40),               -- número/LID (puede ser NULL si no asignado)
    n_clientes    INTEGER,
    activo        BOOLEAN DEFAULT true
);
```
Se carga con el directorio ya capturado (`docs/vendedores_directorio.md`, 44 vendedores).

> **Tools por turno:** se guardan como `TEXT[]` en el evento (simple y filtrable con `unnest`).
> Si más adelante se quieren métricas finas por tool (latencia por tool, etc.), se puede
> normalizar a una tabla `event_tools(event_id, tool)` — pero para el dashboard el array basta.

---

## 4. Cambios en el AGENTE (para poblar la tabla)

1. **Identidad por mensaje:** el `perfil` ya tiene `vendedor_id`, `nombre`, canal en el webhook.
   Pasarlos a la función de guardado (hoy solo se pasa `numero`).
2. **Tools usadas:** extraerlas del estado final del grafo (los `AIMessage.tool_calls`; la
   lógica ya existe en `validar._tools_usadas`). Hacer que `run_agent_graph_full` devuelva
   también la lista de tools, y el webhook la guarda en el evento del `assistant`.
3. **Sesión/conversación (una por vendedor por día):** no hace falta lógica de gap. La
   "conversación" se deriva en la query como `(numero, fecha en Lima)`. Opcional: guardar un
   `session_id` = `md5(numero + fecha_lima)` para joins directos.
4. **Placa/Yahuar:** el relay ya guarda el resultado (fix reciente); marcar esos con `tipo='placa'`.
5. **Timezone:** guardar `ts` como `TIMESTAMPTZ` (UTC) y convertir a `America/Lima` en las queries
   (`ts AT TIME ZONE 'America/Lima'`) para días/horas de mayor uso.
6. **Latencia (opcional):** medir el tiempo agente y guardarlo (útil para un futuro widget).

---

## 5. Backend — API de estadísticas (con filtros)

Nuevos endpoints (protegidos con el mismo login/token del panel), todos aceptan
`?vendedor_id=&desde=&hasta=`:
```
GET /api/panel/stats/resumen        -> {mensajes_totales, conversaciones}
GET /api/panel/stats/evolucion      -> [{semana, mensajes}]
GET /api/panel/stats/por-dia        -> [{dia, mensajes}]        (Lun..Dom, hora Lima)
GET /api/panel/stats/por-hora       -> [{hora, mensajes}]       (0..23, hora Lima)
GET /api/panel/stats/tools          -> [{tool, n, pct}]
GET /api/panel/stats/ranking        -> [{vendedor_id, nombre, mensajes}]
GET /api/panel/stats/sin-uso        -> [{vendedor_id, nombre}]  (roster - con actividad)
GET /api/panel/vendedores           -> lista para el dropdown del filtro
```
Cada uno es un `GROUP BY` sobre `interaction_events` (+ join a `vendedores` para "sin uso").

---

## 6. Front — Dashboard (extender `catu-panel`)

- Agregar navegación de 2 tabs: **Estadísticas** / **Conversaciones** (ya existe el visor).
- Tab Estadísticas: dropdown de vendedor + los 8 widgets. Gráficos con **Canvas puro o SVG**
  (sin librerías pesadas; barras/línea son simples) o una lib mínima si se prefiere.
- Tab Conversaciones: sumar el **buscador** y la **última hora** por chat (ya casi está).
- Mantener el login y el estilo actual.

---

## 7. Migración y backfill

- Migración `003_interaction_events.sql` + `004_vendedores.sql`.
- Backfill: copiar lo que haya en `chat_messages` a `interaction_events` (sin vendedor/tools;
  se completan de aquí en adelante). Alternativa: dejar `chat_messages` como está y crear la
  nueva tabla en paralelo (el visor sigue andando durante la transición).
- Cargar `vendedores` desde el directorio (44).

---

## 8. Fases de ejecución

| Fase | Qué | Toca |
|---|---|---|
| A | Migraciones: `interaction_events` + `vendedores` + carga del roster | BD |
| B | Agente: guardar evento rico (vendedor, canal, tools, session, tz) | agente |
| C | API de stats (8 endpoints con filtros) | agente |
| D | Front: tab Estadísticas (widgets + filtro) y mejoras a Conversaciones | catu-panel |
| E | Backfill + verificación con data real | BD/QA |

---

## 9. Decisiones confirmadas

1. **"Conversación" = una por vendedor por día.** `session_id` = hash(vendedor/numero + fecha-Lima).
   El KPI "Conversaciones" = count de (numero, día) distintos.
2. **Mensajes totales = solo mensajes del vendedor** (rol `user`). Los de Catu (`assistant`) se
   guardan igual para el visor, pero NO cuentan en el KPI ni en el ranking.
3. **"Sin uso" = roster de vendedores con WhatsApp asignado** (hoy los 7 registrados en
   `_MOCK_ASESORES`). La tabla `vendedores` se llena con esos; crece cuando se asignen más números.
4. **Gráficos con Chart.js**, respetando la paleta y el diseño de los PNG (ver §10).

### Defaults aplicados en el resto (ajustables)
- **Filtro de fechas:** se agrega selector de rango (desde/hasta) además del filtro por vendedor.
- **Tools:** se agrupan por las tools reales activas con etiquetas legibles
  (Stock, Precio, Cartera, Cliente, Catálogo, Placa).
- **Zona horaria:** America/Lima (UTC-5) para días/horas de mayor uso.
- **Placas/imágenes:** cuentan como mensajes del vendedor solo si el rol es `user`;
  el resultado de placa (assistant) no cuenta en el KPI. Se marcan con `tipo`.
- **Acceso:** mismo login del panel (una sola contraseña) por ahora.
- **Retención:** todo permanente (sin purga por ahora).

---

## 10. Paleta y diseño (tomados de los PNG)

```
Header / navy      #16233A     (barra superior)
Acento primario    #E8623E     (línea de evolución, barra destacada, ranking, tab activa)
Barras neutras     #CBD5E1     (días/horas sin destacar)
Texto principal    #1E293B
Texto secundario   #64748B
Fondo página       #F4F6F8     Cards #FFFFFF, borde #E5E9ED

Tools (colores del mockup):
  Stock     #3B82F6 (azul)
  Precio    #1FA97F (verde)
  Cliente   #7C6FD6 (morado)
  Cotización/otro #E8623E (coral)
  Historial #8B9199 (gris)
```
- KPIs en cards grandes con número en negrita.
- Barras con label del valor arriba (días) o dentro (tools) + % a la derecha.
- Ranking con avatar circular (iniciales) + barra de progreso coral.
- Tab activa subrayada en coral. Look limpio, mucho blanco, esquinas redondeadas.
