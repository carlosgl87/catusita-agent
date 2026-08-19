"""Área `recomendaciones` de Clientes — Recomendaciones.

Contesta: ¿Qué más me puede servir?
Entidad:  cliente × catálogo

    NO EXPONE (y no puede: el código no mapea esos campos):
      (no aplica)

CONTRATO PÚBLICO: MODELO, NODO, TOOLS. Nadie importa `servicio`, `backend`,
`prompt` ni `agente` desde afuera, y nada de Clientes importa código de
Vendedores.

No le habla a ninguna otra área. Si le falta un dato, se lo pide al orquestador.

    Datos de otras áreas que puede necesitar:
      - `productos` — para el catálogo
"""
from clientes.agentes.recomendaciones.agente import NODO
from clientes.agentes.recomendaciones.tools import TOOLS

# razona sobre historial para sugerir
MODELO = "claude-sonnet-5"

# lookup contra el backend, responde en segundos

# Lo que el orquestador ve de esta área. Es la PREGUNTA que contesta, no
# la lista de sus tools: el orquestador delega en el ÁREA y es ella la que
# decide cuáles usar y en qué orden.
DESCRIPCION = (
    "Qué otros productos le pueden servir al cliente, a partir de lo que consultó o compró antes."
)

__all__ = ["MODELO", "DESCRIPCION", "NODO", "TOOLS"]
