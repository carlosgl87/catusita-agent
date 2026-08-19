"""RAG simple. Un paso hoy, varios mañana.

    async def buscar(consulta):
        vector = await backend.embeber(consulta)      # la consulta del usuario, sin tocar
        procesos = await backend.similares(vector, k=K)
        if not procesos or procesos[0]["similitud"] < UMBRAL:
            await backend.registrar_solicitud(consulta, vector, "sin_resultado", ...)
            return []
        return procesos

`multiagente` ya no es parámetro: la tabla del backend es la de este multiagente.

Los pasos que vendrán se insertan acá, en este orden y midiendo cada uno:

    1. rerank        reordenar los k candidatos con un modelo de reranking
    2. híbrida       sumar búsqueda por texto para códigos y nombres propios
    3. reformular    reescribir la consulta antes de embeber
    4. loop          evaluar lo recuperado y reintentar con otro término

Se agregan de a uno. Con RAG, un cambio que suena obviamente bueno empeora la
recuperación tan seguido como la mejora, y si entran dos juntos no se sabe cuál
fue. Por eso `procesos_aplicados` guarda qué se recuperó y con qué consulta:
sin esa tabla no hay contra qué comparar.
"""

K = 5

# Mismo umbral que plataforma/nodos/contexto.py. Debajo de esto no hay proceso.
UMBRAL = 0.35

# TODO: implementar buscar(). Ver backend.py.
