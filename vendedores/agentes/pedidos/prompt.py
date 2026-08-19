"""System prompt de `pedidos` (vendedores).

Solo carga cuando esta área corre. Sabe de pedido / factura y de nada más.

EL ENCADENAMIENTO «primero consultar_pedidos, luego consultar_despacho» es lógica interna de esta área.
"""

SYSTEM = """TODO: prompt de pedidos y despacho para vendedores.

Contesta: ¿Dónde está el pedido y ya llegó?
"""
