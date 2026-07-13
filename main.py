from fastapi import FastAPI
from contextlib import asynccontextmanager
from webhooks.whatsapp import router_wh as whatsapp_router
from dashboard.panel import router_panel


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Solo inicializar DB si DATABASE_URL está configurado
    import os
    if os.getenv("DATABASE_URL"):
        from db.connection import init_db, close_db
        await init_db()
        yield
        await close_db()
    else:
        yield


app = FastAPI(title="Catusita Agent API", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "catusita-agent"}


app.include_router(whatsapp_router, prefix="/webhook")
app.include_router(router_panel)
