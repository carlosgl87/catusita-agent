"""Embeddings del RAG de procesos. Un cliente por proceso.

Anthropic no ofrece embeddings, así que este es el ÚNICO lugar del sistema donde
se usa OpenAI. El razonamiento sigue siendo de Claude: acá solo se convierte
texto en vectores.

Vive en `plataforma/` y no en cada área por lo mismo que el pool de Redis:
duplicar el cliente abriría N conexiones al mismo servicio sin ganar nada. El
aislamiento entre multiagentes ya lo da la tabla —`conocimiento_vendedores` vs
`conocimiento_clientes`— y no el cliente que las consulta.

── Ojo con el modelo ──────────────────────────────────────────────────────────

Cambiar MODELO invalida TODAS las filas ya embebidas: los vectores viejos y los
nuevos viven en espacios distintos y la similitud entre ellos no significa nada.
No falla, no avisa — solo recupera mal. Por eso cada fila guarda su `modelo_emb`
y por eso `DIMS` se verifica en la primera llamada.
"""
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

MODELO = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Tiene que coincidir con vector(N) en db/migrations/004_conocimiento.sql.
DIMS = 1536

_cliente: AsyncOpenAI | None = None
_dims_verificadas = False


def _get() -> AsyncOpenAI:
    global _cliente
    if _cliente is None:
        clave = os.getenv("OPENAI_API_KEY")
        if not clave:
            raise RuntimeError(
                "Falta OPENAI_API_KEY. Es lo único que el sistema le pide a OpenAI: "
                "los embeddings del RAG de procesos."
            )
        _cliente = AsyncOpenAI(api_key=clave)
    return _cliente


def _verificar(vector: list[float]) -> None:
    """Que el modelo devuelva lo que la columna espera. Una sola vez por proceso.

    Sin esto, un cambio de modelo entra en la tabla en silencio y recién se nota
    semanas después, como «el bot dejó de encontrar los procesos».
    """
    global _dims_verificadas
    if _dims_verificadas:
        return
    if len(vector) != DIMS:
        raise RuntimeError(
            f"{MODELO} devuelve {len(vector)} dims y las tablas conocimiento_* son "
            f"vector({DIMS}). O se cambia el modelo, o se migran las 6 columnas y "
            f"se re-embebe todo lo cargado."
        )
    _dims_verificadas = True


async def embeber(texto: str) -> list[float]:
    """Texto -> vector. Devuelve [] si no hay nada que embeber.

    El [] es deliberado: una consulta vacía no debe convertirse en una búsqueda
    contra un vector de ceros, que devolvería resultados arbitrarios.
    """
    texto = (texto or "").strip()
    if not texto:
        return []
    r = await _get().embeddings.create(model=MODELO, input=texto)
    vector = r.data[0].embedding
    _verificar(vector)
    return vector


async def embeber_lote(textos: list[str]) -> list[list[float]]:
    """Varios de una. Para cargar o re-embeber procesos, no para el camino del chat.

    Una sola llamada con N textos, no N llamadas: es más barato y mucho más
    rápido cuando hay que re-embeber la tabla entera por un cambio de modelo.
    """
    limpios = [(t or "").strip() for t in textos]
    if not any(limpios):
        return [[] for _ in limpios]
    r = await _get().embeddings.create(model=MODELO, input=limpios)
    vectores = [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
    if vectores:
        _verificar(vectores[0])
    return vectores
