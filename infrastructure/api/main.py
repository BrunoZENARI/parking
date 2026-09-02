import logging

from fastapi import FastAPI

from infrastructure.api.routes.parking_routes import router as parking_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Micro-service Parking",
    description=(
        "Gestion du stock de places par catégorie.\n\n"
        "Autorité sur la disponibilité des places du parking. "
        "Expose une API REST pour les besoins synchrones (disponibilité, hold, libération) "
        "et consomme des événements RabbitMQ pour les confirmations d'entrée/sortie."
    ),
    version="1.0.0",
)

app.include_router(parking_router)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "parking"}


@app.on_event("startup")
async def startup():
    logger.info("Démarrage du micro-service Parking")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Arrêt du micro-service Parking")
