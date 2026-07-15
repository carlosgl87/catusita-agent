# Carpeta de mejoras del agente Catusita (README)

Este es el **tablero de mejoras**: registra cada incidencia (dolor) del agente, la
mejora propuesta y su estado (Pendiente / Aplicado / Rechazado).

> **El proceso lo ejecuta el skill `/mejoras-catusita`.** Ese skill es la única
> fuente de verdad del "cómo" (leer los chats, detectar dolores nuevos, y el loop
> de aprobación). Este archivo es solo una guía para entender la carpeta.

## Archivos

| Archivo | Qué es |
|---|---|
| `incidencias.json` | La **fuente de verdad**: la lista de incidencias con su estado. |
| `incidencias.xlsx` | La **vista** para revisar (se genera desde el JSON). |
| `gen_excel.py` | Regenera el Excel desde el JSON (`python gen_excel.py`). |
| `INSTRUCCIONES.md` | Este README. |

## Columnas del Excel

`#` · `Área` · **Incidencia** (qué falla) · **Mejora propuesta** · **Resumen en
simple** (no técnico) · **Estado** (Pendiente 🟡 / Aplicado 🟢 / Rechazado 🔴).

## ⚠️ Regla de oro

**Ningún cambio se implementa sin la aprobación explícita del usuario.** El agente
propone; el usuario decide. Cada incidencia se trata de a una, y el Excel siempre
refleja el estado real.

## Cómo usarlo

Pedir *"revisá las mejoras"* o correr **`/mejoras-catusita`**: el skill busca dolores
nuevos en los chats, te muestra solo los nuevos, y arranca el loop de aprobación.
