import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from tortoise.contrib.fastapi import register_tortoise

from infrastructure.api.logging_config import CorrelationIdMiddleware, setup_logging
from infrastructure.api.routes.parking_routes import DEFAULT_CATEGORIES, category_repo
from infrastructure.api.routes.parking_routes import router as parking_router

setup_logging()

logger = logging.getLogger(__name__)

VERSION = "1.5.0"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite://db/parking.db")

app = FastAPI(
    title="Micro-service Parking",
    description=(
        "Gestion du stock de places par catégorie.\n\n"
        "Autorité sur la disponibilité des places du parking. "
        "Expose une API REST pour les besoins synchrones (disponibilité, hold, entrée, libération). "
        "L'intégration RabbitMQ est prévue."
    ),
    version=VERSION,
)

app.add_middleware(CorrelationIdMiddleware)
app.include_router(parking_router)
app.mount("/static", StaticFiles(directory="infrastructure/api/static"), name="static")

register_tortoise(
    app,
    db_url=DATABASE_URL,
    modules={"models": ["infrastructure.persistence.sqlite.models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "parking", "version": VERSION}


@app.get("/dashboard", tags=["UI"])
async def dashboard():
    return FileResponse("infrastructure/api/static/dashboard.html")


@app.on_event("startup")
async def startup():
    logger.info("Démarrage du micro-service Parking (version %s)", VERSION)
    await category_repo.get_or_create_all(DEFAULT_CATEGORIES)
    logger.info("Catégories initialisées en base")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Arrêt du micro-service Parking")