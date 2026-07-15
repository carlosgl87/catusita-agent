---
name: mejoras-catusita
description: Gestiona el tablero de mejoras del agente Catusita (mejoras/). Lee los chats reales, detecta los "dolores" (fallas/fricciones), los registra como incidencias, y recorre las pendientes una por una presentando cada mejora en lenguaje simple, ESPERANDO la aprobación explícita del usuario antes de aplicar y actualizar el estado (Aplicado/Rechazado) en incidencias.json + el Excel. Usar cuando el usuario pida "revisar mejoras", "detectar dolores en los chats", "gestionar incidencias" o invoque /mejoras-catusita.
---

# Skill — Gestión de mejoras del agente Catusita

Tablero en [`mejoras/`](../../../mejoras/). Proceso completo en
[`mejoras/INSTRUCCIONES.md`](../../../mejoras/INSTRUCCIONES.md).

## Al activarse el skill (ENTRADA — hacer esto primero)

1. **Leer** los chats (sección 1) y `incidencias.json` (lo ya registrado).
2. **Detectar dolores NUEVOS** (sección 2) — es decir, los que **no** estén ya en
   `incidencias.json`. Ignorar cualquier dolor cuya causa raíz ya esté registrada,
   **sin importar su estado** (Pendiente, Aplicado o Rechazado). Nunca volver a
   mostrar las incidencias viejas ni las ya resueltas.
3. **Mostrar al usuario SOLO las incidencias nuevas** encontradas, en una lista
   breve y clara (qué falla + mejora propuesta + resumen en simple). Si no hay
   ninguna nueva, decirlo ("no encontré dolores nuevos desde la última revisión").
4. Registrarlas como `Pendiente`, regenerar el Excel y recién ahí entrar al
   **loop de aprobación** (sección 3), de a una.

Flujo global: **leer chats → detectar dolores NUEVOS → mostrarlos al usuario →
registrar → loop de aprobación → aplicar y marcar en el Excel.**

---

## 1. Acceso a los datos (los chats)

Los mensajes viven en la tabla `chat_messages` del Postgres del proyecto Railway
`agent-catu`. Dos formas de leerlos:

### Vía API del panel (recomendado)
```
BASE = https://catusita-agent-production-3650.up.railway.app
# 1) contraseña (no está hardcodeada): sacarla de Railway
railway variables -s catusita-agent   → variable PANEL_PASSWORD
# 2) login → token
POST {BASE}/api/panel/login   body {"password": "<PANEL_PASSWORD>"}   → {token}
# 3) lista de conversaciones
GET  {BASE}/api/panel/chats                 (Header: Authorization: Bearer <token>)
# 4) mensajes de un chat
GET  {BASE}/api/panel/chats/{numero}        → { mensajes: [{rol, contenido, created_at}] }
```

### Vía BD directa (alternativa)
Tabla `chat_messages`: `numero, vendedor_id, vendedor_nombre, rol, contenido,
tools[], tipo, created_at`. `rol='user'` = vendedor, `rol='assistant'` = Catu.
Consultar con el `DATABASE_URL` del servicio `catusita-agent`.

---

## 2. Cómo detectar los "dolores" en los chats

Recorrer los chats buscando **señales de fricción** y, por cada una, confirmar la
causa antes de registrarla.

### Señales a buscar (en orden de prioridad)

**① El usuario declara el error / insiste — la señal más fuerte.** Es un dolor
confirmado por la propia fuente, no una suposición. Priorizar SIEMPRE estos casos:
- Corrige o contradice al agente: "eso no es", "está mal", "te equivocas",
  "no es correcto", "sí hay, mira bien", "revisa bien", "fíjate de nuevo".
- Se queja: "no me ayudas", "no sirve", "no me sirve", "otra vez lo mismo".
- **Insiste:** repite la misma consulta (igual o reformulada) porque la respuesta
  anterior no le sirvió. La insistencia = el agente falló y el usuario lo marca.

**② Respuesta de falla del agente** (pista secundaria): "no encontré", "no está en
el catálogo", "consulta con tu jefe de línea", "no disponible", "sin resultados".

**③ Consulta sin cerrar:** el pedido nunca llegó a una respuesta útil y el chat corta.

> El dolor real es el del punto ①: donde el usuario **explícitamente** dice que la
> respuesta estuvo mal o incompleta. Esos intercambios son los que hay que extraer,
> confirmar y convertir en incidencia.

### Procedimiento por cada dolor (estructurado)
1. **Aislar** el intercambio: qué pidió el vendedor y qué respondió el agente.
2. **Confirmar la causa — no asumir.** Reproducir contra la fuente real (ej. probar
   el buscador `tools-agente-catusita/catalogo?q=...` con el término y variantes).
   Distinguir "el dato no existe" de "el sistema no lo encontró".
3. **Formular la incidencia:** qué falla (observable + evidencia), causa probable,
   y una mejora concreta y acotada.
4. **Escribir el resumen en simple** (cómo mejora, sin jerga técnica).
5. **Registrar** en `incidencias.json` como `Pendiente` (id nuevo, área, fecha) y
   regenerar el Excel (`python mejoras/gen_excel.py`).
6. **Solo nuevos — no duplicar:** antes de crear una incidencia, revisar
   `incidencias.json`. Si la misma causa raíz ya figura (aunque esté `Aplicado` o
   `Rechazado`), **no** crearla de nuevo ni mostrarla; a lo sumo agrupar evidencia
   en la existente. Solo se registran y presentan dolores realmente nuevos.

---

## 3. Loop de aprobación

Para cada incidencia `Pendiente` (menor `id` primero), de a una:

1. **Presentar** al usuario: qué falla, la mejora propuesta y el resumen en simple.
2. **⚠️ ESPERAR su decisión. NO aplicar nada antes.**
   - Aprobar → aplicar, verificar, marcar `Aplicado`.
   - Rechazar → marcar `Rechazado` (no aplicar).
   - Pedir ajustes → revisar la propuesta y volver a presentar.
3. **Actualizar** `incidencias.json` (`estado` + `fecha`) y **regenerar el Excel**:
   `python mejoras/gen_excel.py` (Python con `openpyxl`, ej. el venv de tools_agente_catusita).
4. **Confirmar:** "Incidencia N — Aplicada ✅" o "Rechazada".
5. Seguir con la siguiente.

---

## Reglas de oro

- **Ningún cambio se implementa sin aprobación explícita del usuario.**
- **Una incidencia a la vez** — no aplicar varias de golpe.
- El Excel siempre refleja el estado real: **Pendiente / Aplicado / Rechazado**.
- Antes de registrar un dolor, **confirmar la causa con evidencia** (reproducir).
