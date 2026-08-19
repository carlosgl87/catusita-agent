# Recepción — lo único que mira a internet.
#
#   recepcion/
#     main.py       la app FastAPI
#     webhook.py    recibe de WAHA y valida
#     router.py     a qué multiagente va
#     numeros.py    normalización y sesiones
#     padron.py     lee el mapa numero -> multiagente
#     acumulador.py junta los fragmentos antes de encolar
#     contrato.py   el sobre que cruza a los workers
#     waha.py       manda las respuestas
#     redis.py      pool
#
# NO entra ningún multiagente: acá no corre ningún agente ni se toca Postgres.
FROM python:3.13-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY recepcion/ ./recepcion/

EXPOSE 8080
CMD ["uvicorn", "recepcion.main:app", "--host", "0.0.0.0", "--port", "8080"]
