# Multiagente vendedores. Se copia UNA carpeta y adentro está todo.
#
#   vendedores/
#     orquestador.py          quién coordina
#     grafo.py                cómo se conectan los nodos
#     registro.py             descubre sus áreas
#     chat.py                 su tabla de mensajes
#     agentes/                un área por carpeta: prompt, subgrafo, tools,
#                             backend, contratos y tests
#     plataforma_vendedores/   su plomería: pools, colas, contrato,
#                             acumulador, estado y nodos compartidos
#
# NO entra nada de los otros multiagentes. No hay carpeta compartida que copiar:
# si esta imagen se construye, este multiagente corre.
FROM python:3.13-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vendedores/ ./vendedores/

CMD ["python", "-m", "vendedores.plataforma_vendedores.worker"]
