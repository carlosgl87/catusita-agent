"""Multiagente Vendedores — Asesores comerciales internos de Catusita.

Acceso completo: precio neto, cartera, pedidos, documentos y cobranza.

Es un proyecto aparte de `clientes` y `supervisores`. No comparten agentes, ni
prompts, ni acceso a datos: solo `plataforma/` (LLM, Redis, DB, transporte) y el
`router/` que decide a cuál de los tres entra el mensaje.

Áreas: productos, vehiculos, clientes, pedidos, facturacion, conocimiento
"""
