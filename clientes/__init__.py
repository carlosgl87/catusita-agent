"""Multiagente Clientes — Talleres, distribuidores y consumidor final.

Solo información pública: stock, precio de lista, catálogo y reclamos.

Es un proyecto aparte de `vendedores` y `supervisores`. No comparten agentes, ni
prompts, ni acceso a datos: solo `plataforma/` (LLM, Redis, DB, transporte) y el
`router/` que decide a cuál de los tres entra el mensaje.

Áreas: productos, vehiculos, postventa, recomendaciones, conocimiento
"""
