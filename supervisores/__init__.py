"""Multiagente Supervisores — Jefes de venta que consultan sobre su equipo.

OJO: este archivo era una copia literal del de vendedores —misma audiencia,
mismas áreas— y decía cosas que no son de este multiagente. Corregido.

Hoy tiene UNA sola área: `conocimiento`. No tiene áreas de datos propias porque
falta resolver la pregunta de fondo: si un supervisor puede ver la cartera y las
cifras de SUS asesores. Eso toca el aislamiento de acceso y no se decidió, así
que mientras tanto este multiagente solo consulta procedimientos.

Es un proyecto aparte de `vendedores` y `clientes`. No comparten agentes, ni
prompts, ni acceso a datos: solo `plataforma/` (LLM, Redis, DB, transporte) y el
`router/` que decide a cuál de los tres entra el mensaje.

Áreas: conocimiento
"""
