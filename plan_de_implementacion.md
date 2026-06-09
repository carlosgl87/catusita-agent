# Plan de Implementación — QA Agente Vendedores (Catu)

> Objetivo: cerrar las brechas entre el comportamiento que exige `QA_agente.md` y
> lo que hoy hace el código, de modo que el **Agente Vendedores** pase todas las
> preguntas de prueba (incluyendo las que NO debe responder y las que debe derivar).
>
> Proyectos involucrados:
> - **`railway mcp`** (catusita-agent): el agente WhatsApp. Aquí van casi todos los cambios.
> - **`mockup-catusita`** (Mock SAP): solo se toca si decidimos endpoints P2 (opcional, ver Fase 4).

---

## 0. Resumen de brechas (qué exige el QA vs. qué hay hoy)

| # | Comportamiento esperado por el QA | Estado hoy | Acción |
|---|-----------------------------------|------------|--------|
| 1 | Validar que el cliente consultado sea de la cartera del asesor; rechazar clientes ajenos | **Sin enforcement** — solo una regla en el prompt, el LLM ni sabe qué RUCs son suyos | **Fase 1 — código** |
| 2 | NO revelar almacén/distrito del stock | El dato no existe en el Mock SAP; el prompt no lo prohíbe (riesgo de alucinación) | **Fase 2 — prompt** |
| 3 | NO revelar hora de reparto / local de despacho | El dato no existe; el prompt no lo prohíbe | **Fase 2 — prompt** |
| 4 | Reposición de producto agotado (P2): indicar que no está disponible / derivar al jefe de línea | Sin tool ni endpoint; regla genérica | **Fase 2 — prompt** |
| 5 | Antigüedad de mercadería +6 meses (P2): indicar que no está disponible | Sin tool ni endpoint | **Fase 2 — prompt** |
| 6 | Descuento por volumen → derivar | Parcial (el prompt menciona "descuentos") | **Fase 2 — prompt** |
| 7 | Precio por zona/provincia → derivar | No cubierto | **Fase 2 — prompt** |
| 8 | Precio neto sin IGV → NO responder | ✅ El dispatch fuerza `tipo="lista"` + regla en prompt | OK (verificar en pruebas) |
| 9 | Excepción de crédito → derivar a créditos | Regla genérica | **Fase 2 — prompt** |
| 10 | Precio especial fuera de lista → derivar | Parcial | **Fase 2 — prompt** |
| 11 | Reclamo (cliente equivocado, etc.) → derivar / tomar datos | El vendedor no tiene tool de reclamo | **Fase 2 — prompt** |
| 12 | No inventar precios/stocks/fechas | ✅ Regla en prompt | OK (verificar) |
| 13 | Pagos: ¿pagado? ¿factura pendiente? ¿cuánto debe y cuándo vence? | Funciona vía `consultar_cobranzas` / `obtener_documentos` | OK (verificar) |

**Conclusión:** el grueso es **(A) un control de acceso por cartera a nivel de código** y
**(B) endurecer el system prompt del vendedor**. Lo demás es verificación.

---

## Fase 1 — Control de acceso por cartera (lo más importante)

**Problema:** cualquier `cliente_ruc` que el modelo coloque en una tool llega tal cual al
Mock SAP, que responde sin importar a qué vendedor pertenece el cliente. Esto rompe los
casos del QA:
- "¿Me puedes decir el estado de cuenta del cliente 12345?" *(debe validar que sea de su cartera)*
- "¿Puedes decirme info de un cliente que no es mío?" *(debe rechazar)*

**Solución:** validar el RUC contra la cartera del asesor **en el código**, antes de llamar
al Mock SAP. No confiar solo en el prompt.

### 1.1 Archivo: `orchestrator/router.py`

Agregar, encima de `execute_tool`, el set de tools "scopeadas por RUC" y un helper con caché:

```python
# Tools cuyo RUC debe pertenecer a la cartera del asesor antes de ejecutarse.
# El valor es el nombre del argumento que contiene el RUC.
RUC_SCOPED_TOOLS = {
    "consultar_credito": "cliente_ruc",
    "consultar_cobranzas": "cliente_ruc",
    "consultar_historial": "cliente_ruc",
    "consultar_pedidos": "cliente_ruc",
    "obtener_documentos": "cliente_ruc",
    "consultar_perfil_cliente": "ruc",
}


async def _rucs_de_cartera(perfil: dict) -> set:
    """RUCs de la cartera del asesor, cacheados en el perfil para no repetir llamadas."""
    cache = perfil.get("_cartera_rucs")
    if cache is not None:
        return cache
    data = await cartera.consultar_cartera(perfil.get("vendedor_id", "V001"))
    rucs = {c["ruc"] for c in data.get("clientes", [])} if isinstance(data, dict) else set()
    perfil["_cartera_rucs"] = rucs
    return rucs
```

Dentro de `execute_tool`, **antes** de `fn = dispatch.get(name)`, insertar la validación
(solo aplica a asesores):

```python
    # --- Control de acceso por cartera (solo asesores) ---
    arg_ruc = RUC_SCOPED_TOOLS.get(name)
    if arg_ruc and perfil.get("tipo") == "asesor":
        ruc = (args.get(arg_ruc) or "").strip()
        if ruc and ruc not in await _rucs_de_cartera(perfil):
            return {
                "error": "ACCESO_DENEGADO",
                "mensaje": (
                    "Ese cliente no pertenece a tu cartera asignada. "
                    "Solo puedo darte información de tus propios clientes."
                ),
            }
```

> **Nota de diseño:** se cachea la cartera en `perfil["_cartera_rucs"]` durante el turno
> para no llamar al Mock SAP en cada tool. El `perfil` ya se pasa por referencia a
> `execute_tool` (igual que `_media_pendiente`), así que es seguro.

### 1.2 Reforzar el `tool_result` de acceso denegado en el prompt

Cuando el modelo recibe `{"error": "ACCESO_DENEGADO", ...}`, debe responder con el mensaje,
no reintentar. Se cubre con la regla de prompt de la Fase 2 ("si una tool devuelve
ACCESO_DENEGADO, comunica el mensaje y no insistas").

### 1.3 (Opcional pero recomendado) datos de prueba alineados

Para que el QA sea verificable, conviene tener a mano **2 RUCs reales de la cartera de V001**
y **1 RUC que NO sea de V001**. Como el Mock SAP genera datos con Faker(seed=42), obténlos así
(ver `plan_de_prueba.md`, sección "Preparación de datos"). Anótalos en un `.env.test` o en la
cabecera del plan de pruebas.

---

## Fase 2 — Endurecer el system prompt del Vendedor

**Archivo:** `orchestrator/router.py` → constante `SYSTEM_VENDEDOR`.

Reemplazar el bloque de "Reglas importantes" por una versión que cubra explícitamente cada
caso del QA. Mantener las reglas que ya funcionan (cartera, nombre→RUC, precio neto) y **añadir**:

```text
Reglas de privacidad y alcance (OBLIGATORIAS):
- NUNCA reveles en qué almacén, local, distrito o ubicación física está un producto o un
  despacho. Si te lo preguntan, responde: "No manejo la ubicación física del stock ni del
  despacho; coordina eso con logística."
- NUNCA reveles la hora de salida del reparto ni desde qué local se despacha. Deriva a logística.
- Si una tool devuelve un error con "ACCESO_DENEGADO", comunica su mensaje tal cual y NO
  reintentes con otra tool ni inventes datos.

Funcionalidades aún no disponibles (P2) — di que todavía no están y deriva:
- Fecha de reposición / reabastecimiento de producto agotado: "Aún no tengo conectada la
  fecha de reposición. Confírmala con tu jefe de línea."
- Antigüedad de mercadería en almacén (productos con +90 días / +6 meses): "Ese reporte
  todavía no está disponible en el asistente."

Derivaciones (NO resuelvas tú, deriva al área correcta):
- Descuento por volumen / precio especial fuera de lista / precio diferenciado por zona o
  provincia → "Eso se coordina con tu jefe de línea; yo solo manejo precio de lista."
- Excepción o ampliación de crédito → "Las excepciones de crédito las aprueba el área de
  créditos; deriva el caso ahí."
- Reclamo o devolución (producto equivocado, dañado, etc.) → toma los datos del pedido y el
  motivo y di: "Voy a registrar el caso para que atención al cliente lo gestione." (el vendedor
  no resuelve el reclamo).

Anti-alucinación:
- Si no tienes el dato vía una tool, di explícitamente que no lo tienes. NUNCA inventes
  precios, stocks, fechas, números de pedido ni datos de clientes.
```

> Mantener también las reglas existentes de precio neto y de cartera; este bloque se **suma**.

---

## Fase 3 — (Opcional) Tool explícita de derivación de reclamo para el vendedor

Hoy `registrar_reclamo` solo está en `TOOLS_CLIENTES`. El QA del vendedor dice "debe derivar
o iniciar flujo de reclamo", y con la regla de prompt de la Fase 2 **ya se cumple** (el agente
toma datos y dice que lo deriva). 

Solo si el negocio quiere que el vendedor **genere número de caso**, agregar `registrar_reclamo`
a `TOOLS_VENDEDORES` y al `dispatch` (reusando `agents/claims.py`). **Recomendación:** dejarlo
para una segunda iteración; con el prompt basta para pasar el QA.

---

## Fase 4 — (Opcional) Endpoints P2 en el Mock SAP

Solo si se decide implementar de verdad reposición y antigüedad (en vez de "no disponible"):
- `mockup-catusita/main.py` + `data/productos.py`: agregar `GET /reposicion/{sku}` y
  `GET /antiguedad`.
- `railway mcp`: nuevas tools + agentes.

**Recomendación:** NO hacerlo ahora. El QA marca ambas como P2 y espera "no disponible aún".
Implementar el endpoint contradiría el resultado esperado del QA.

---

## Orden de ejecución y archivos tocados

1. **Fase 1** — `orchestrator/router.py` (control de acceso por cartera). *(Core, ~30 líneas.)*
2. **Fase 2** — `orchestrator/router.py` (endurecer `SYSTEM_VENDEDOR`). *(Solo texto.)*
3. **Verificación local** — `python test_terminal.py vendedor` recorriendo `plan_de_prueba.md`.
4. **Fase 3 / 4** — solo si el negocio lo pide.

**Archivos que NO se tocan:** `main.py`, `webhooks/whatsapp.py`, `orchestrator/context.py`,
`db/`, `shared/` (salvo que se agregue reclamo de vendedor), todo `mockup-catusita` (salvo P2).

---

## Criterios de aceptación (Definition of Done)

- [ ] Un asesor consultando crédito/cobranzas/pedidos/historial/documentos/perfil de un RUC
      **fuera de su cartera** recibe un rechazo claro y el agente NO muestra datos.
- [ ] El agente nunca menciona almacén, distrito, local ni hora de reparto.
- [ ] Reposición y antigüedad responden "no disponible aún" / derivan, sin inventar fechas.
- [ ] Descuento por volumen, precio especial, precio por zona y precio neto → derivan, nunca dan número.
- [ ] Excepción de crédito → deriva a créditos; reclamo → toma datos y deriva.
- [ ] Ningún caso del `plan_de_prueba.md` produce datos inventados.
- [ ] Las consultas válidas (stock, precio lista, pedidos propios, cobranzas propias,
      documentos propios, cartera, catálogo, vehículo/placa) siguen funcionando igual.
</content>
</invoke>
