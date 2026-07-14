import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from webhooks.whatsapp import router_wh as whatsapp_router
from dashboard.panel import router_panel


async def _sync_vendedores():
    """Carga el roster de vendedores (para 'sin uso' y el filtro) desde el registro de auth."""
    from shared import auth
    from db import models
    vistos = set()
    for numero, p in auth._MOCK_ASESORES.items():
        vid = p.get("vendedor_id")
        if not vid or vid in vistos:
            continue
        vistos.add(vid)
        try:
            await models.upsert_vendedor(vid, p.get("asesor_id"), p.get("nombre"), numero)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Solo inicializar DB si DATABASE_URL está configurado
    if os.getenv("DATABASE_URL"):
        from db.connection import init_db, close_db
        await init_db()
        await _sync_vendedores()
        yield
        await close_db()
    else:
        yield


app = FastAPI(title="Catusita Agent API", lifespan=lifespan)

# CORS para el front Vite (otro origen). Con Bearer (sin cookies) '*' es seguro.
# Configurable con PANEL_CORS (lista separada por comas) si se quiere restringir.
_cors = os.getenv("PANEL_CORS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _cors == "*" else [o.strip() for o in _cors.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "catusita-agent"}


app.include_router(whatsapp_router, prefix="/webhook")
app.include_router(router_panel)
