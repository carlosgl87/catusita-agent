#!/bin/sh
set -e

echo "Corriendo migraciones..."
python -c "
import asyncio
from db.connection import init_db, close_db

async def migrate():
    await init_db()
    await close_db()

asyncio.run(migrate())
"
echo "Migraciones OK."

echo "Iniciando servidor FastAPI en puerto 8080..."
exec uvicorn main:app --host 0.0.0.0 --port 8080
