#!/bin/sh
set -e

# Las migraciones NO se corren acá.
#
# Antes este script llamaba a init_db(), que reejecutaba TODOS los .sql en cada
# arranque. Las tablas dropeadas a mano volvían solas en el siguiente deploy,
# sin un solo error — `users`, `conversations`, `messages` y `claims` habrían
# reaparecido.
#
# Los .sql de db/migrations/ se aplican a mano, desde desarrollo, cuando se
# decide cambiar el esquema. La tabla `migraciones` registra cuáles ya
# corrieron.

echo "Iniciando servidor FastAPI en puerto 8080..."
exec uvicorn main:app --host 0.0.0.0 --port 8080
