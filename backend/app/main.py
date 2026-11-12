import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .account import router as account_router
from .campaigns import router as campaigns_router
from .config import is_production, settings
from .database import SessionLocal, initialize_schema
from .forms import router as forms_router
from .inbox import router as inbox_router
from .library import router as library_router
from .public_forms import router as public_forms_router
from .sales import router as sales_router
from .security import ensure_production_secrets
from .seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Les mesures de Luna (duree, tentatives, tokens) doivent etre visibles.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    # Avant la base : un démarrage en production avec la clé de développement
    # rendrait les jetons et le cookie de parcours forgeables.
    ensure_production_secrets()
    initialize_schema()
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Sillage API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(sales_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "demo": not is_production()}


app.include_router(account_router)
app.include_router(campaigns_router)
app.include_router(forms_router)
app.include_router(library_router)
app.include_router(inbox_router)
app.include_router(public_forms_router)
