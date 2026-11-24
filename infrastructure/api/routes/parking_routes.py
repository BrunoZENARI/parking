import logging
import os
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from infrastructure.api.security import verify_api_key
from pydantic import BaseModel

from domain.entities.category import Category, CommercialType
from domain.entities.temporary_hold import HoldStatus, TemporaryHold
from infrastructure.persistence.sqlite.category_repository_impl import SQLiteCategoryRepository
from infrastructure.persistence.sqlite.temporary_hold_repository_impl import SQLiteTemporaryHoldRepository
from infrastructure.api import metrics

_stock_lock = asyncio.Lock()


async def serialize_stock():
    """Une seule opération sur le stock à la fois (évite les courses entre requêtes)."""
    async with _stock_lock:
        yield


router = APIRouter(
    prefix="/parking",
    tags=["Parking"],
    dependencies=[Depends(verify_api_key), Depends(serialize_stock)],
)

HOLD_TIMEOUT_SECONDS = int(os.getenv("HOLD_TIMEOUT_SECONDS", 30))
logger = logging.getLogger("parking.metier")

# Catégories par défaut — créées en base au démarrage si absentes
DEFAULT_CATEGORIES: dict[str, Category] = {
    "STANDARD":    Category(name="STANDARD",    total_capacity=80, walkin_capacity=70, booking_capacity=10),
    "HANDICAPPED": Category(name="HANDICAPPED", total_capacity=6,  walkin_capacity=6,  booking_capacity=0),
    "ELECTRIC":    Category(name="ELECTRIC",    total_capacity=12, walkin_capacity=12, booking_capacity=0),
    "XL":          Category(name="XL",          total_capacity=12, walkin_capacity=10, booking_capacity=2),
    "TWO_WHEELS":  Category(name="TWO_WHEELS",  total_capacity=10, walkin_capacity=10, booking_capacity=0),
}

CATEGORY_LABELS = {
    "STANDARD":    "Standard",
    "HANDICAPPED": "PMR",
    "ELECTRIC":    "Électrique",
    "XL":          "XL",
    "TWO_WHEELS":  "Deux-roues",
}


def get_label(name: str) -> str:
    return CATEGORY_LABELS.get(name.upper(), name.title())


category_repo = SQLiteCategoryRepository()
hold_repo = SQLiteTemporaryHoldRepository()


# --- Schémas Pydantic ---

class AvailabilityResponse(BaseModel):
    category_name: str
    label: str
    commercial_type: str
    is_available: bool
    spot_available: int


class HoldRequest(BaseModel):
    category_name: str
    commercial_type: CommercialType


class HoldResponse(BaseModel):
    hold_id: int
    category_name: str
    label: str
    commercial_type: str
    end_at: str
    success: bool


class EntryExitRequest(BaseModel):
    category_name: str
    commercial_type: CommercialType


class ConfirmEntryRequest(BaseModel):
    category_name: str
    commercial_type: CommercialType
    hold_id: int


class OccupationResponse(BaseModel):
    category_name: str
    label: str
    occupation_rate: float
    spot_taken: int
    total_capacity: int
    spot_held: int
    booking_capacity: int
    spot_taken_walkin: int
    spot_taken_booking: int
    spot_held_walkin: int
    spot_held_booking: int


class AllCategoriesResponse(BaseModel):
    categories: list[OccupationResponse]


class CategoryInfoResponse(BaseModel):
    category_name: str
    label: str


# --- Helpers ---

def _held_walkin(c: Category) -> int:
    return max(0, c.walkin_capacity - c.spot_taken_walkin - c.spot_available_walkin)


def _held_booking(c: Category) -> int:
    return max(0, c.booking_capacity - c.spot_taken_booking - c.spot_available_booking)


def _held(c: Category) -> int:
    """Places en attente (holds actifs) = stock virtuel retiré mais pas encore confirmé."""
    return _held_walkin(c) + _held_booking(c)


def _to_occupation(c: Category, name: str | None = None) -> OccupationResponse:
    n = name or c.name
    return OccupationResponse(
        category_name=n,
        label=get_label(n),
        occupation_rate=c.occupation_rate(),
        spot_taken=c.spot_taken_walkin + c.spot_taken_booking,
        total_capacity=c.total_capacity,
        spot_held=_held(c),
        booking_capacity=c.booking_capacity,
        spot_taken_walkin=c.spot_taken_walkin,
        spot_taken_booking=c.spot_taken_booking,
        spot_held_walkin=_held_walkin(c),
        spot_held_booking=_held_booking(c),
    )


async def _cleanup_expired_holds(category: Category, category_name: str):
    category_id = await category_repo.get_id_by_name(category_name)
    expired = await hold_repo.get_expired_active()
    released = False
    for hold in expired:
        if hold.category_id != category_id:
            continue
        hold.status = HoldStatus.EXPIRED
        await category.release_hold(hold.commercial_type)
        await hold_repo.save(hold)
        logger.info("hold %s expiré, place rendue (%s/%s)", hold.id, category_name, hold.commercial_type.value)
        metrics.HOLDS_EXPIRED.labels(category_name, hold.commercial_type.value).inc()
        released = True
    if released:
        await category_repo.save(category)


# --- Routes ---

@router.get(
    "/availability/{category_name}/{commercial_type}",
    response_model=AvailabilityResponse,
    summary="Vérifier la disponibilité d'une catégorie",
)
async def check_availability(category_name: str, commercial_type: CommercialType):
    category = await category_repo.get_by_name(category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {category_name} introuvable")

    await _cleanup_expired_holds(category, category_name.upper())

    if commercial_type == CommercialType.WALKIN:
        spot_available = category.spot_available_walkin
    else:
        spot_available = category.spot_available_booking

    return AvailabilityResponse(
        category_name=category_name.upper(),
        label=get_label(category_name),
        commercial_type=commercial_type,
        is_available=category.is_available(commercial_type),
        spot_available=spot_available,
    )


@router.post(
    "/hold",
    response_model=HoldResponse,
    status_code=201,
    summary="Créer un hold temporaire sur une place",
)
async def create_hold(request: HoldRequest):
    name_upper = request.category_name.upper()
    category = await category_repo.get_by_name(request.category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    await _cleanup_expired_holds(category, request.category_name.upper())

    success = await category.take(request.commercial_type)
    if not success:
        logger.warning("hold refusé : plus de place (%s/%s)", name_upper, request.commercial_type.value)
        metrics.HOLDS_CREATED.labels(name_upper, request.commercial_type.value).inc()
        metrics.HOLDS_REFUSED.labels(name_upper, request.commercial_type.value).inc()
        raise HTTPException(status_code=409, detail="Aucune place disponible")

    await category_repo.save(category)

    now = datetime.now(timezone.utc)
    hold = TemporaryHold(
        id=0,
        category_id=await category_repo.get_id_by_name(request.category_name.upper()),
        commercial_type=request.commercial_type,
        status=HoldStatus.ACTIVE,
        created_at=now,
        end_at=now + timedelta(seconds=HOLD_TIMEOUT_SECONDS),
    )
    saved_hold = await hold_repo.save(hold)
    logger.info("hold %s créé (%s/%s)", saved_hold.id, name_upper, request.commercial_type.value)

    return HoldResponse(
        hold_id=saved_hold.id,
        category_name=request.category_name.upper(),
        label=get_label(request.category_name),
        commercial_type=request.commercial_type,
        end_at=saved_hold.end_at.isoformat(),
        success=True,
    )


@router.post(
    "/confirm_entry",
    status_code=200,
    summary="Confirmer l'entrée d'un véhicule (nécessite un hold actif)",
)
async def confirm_entry(request: ConfirmEntryRequest):
    name = request.category_name.upper()
    category = await category_repo.get_by_name(name)
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    # Les holds expirés sont d'abord nettoyés, puis on relit celui demandé
    await _cleanup_expired_holds(category, name)

    hold = await hold_repo.get_by_id(request.hold_id)
    if not hold:
        raise HTTPException(status_code=404, detail=f"Hold {request.hold_id} introuvable")

    category_id = await category_repo.get_id_by_name(name)
    if hold.category_id != category_id or hold.commercial_type != request.commercial_type:
        metrics.ENTRIES_CONFIRMED.labels(name, request.commercial_type.value).inc()
        metrics.ENTRIES_REFUSED.labels(name, request.commercial_type.value).inc()
        raise HTTPException(status_code=409, detail="Le hold ne correspond pas à la catégorie ou au type demandés")

    if hold.status != HoldStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Hold expiré ou déjà utilisé")

    if not await category.confirm_entry(request.commercial_type):
        logger.warning("entrée refusée : capacité atteinte (%s/%s)", name, request.commercial_type.value)
        raise HTTPException(status_code=409, detail="Capacité atteinte, entrée refusée")

    hold.confirm()
    await hold_repo.save(hold)
    await category_repo.save(category)
    logger.info("entrée confirmée (hold %s, %s/%s)", hold.id, name, request.commercial_type.value)
    return {"message": "Entrée confirmée"}


@router.post(
    "/free",
    status_code=200,
    summary="Libérer une place suite à une sortie",
)
async def free_spot(request: EntryExitRequest):
    category = await category_repo.get_by_name(request.category_name.upper())
    if not category:
        metrics.ENTRIES_REFUSED.labels(name, request.commercial_type.value).inc()
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    await category.free(request.commercial_type)
    await category_repo.save(category)
    logger.info("place libérée (%s/%s)", request.category_name.upper(), request.commercial_type.value)
    metrics.EXITS.labels(request.category_name.upper(), request.commercial_type.value).inc()
    return {"message": "Place libérée avec succès"}


@router.get(
    "/occupation/{category_name}",
    response_model=OccupationResponse,
    summary="Taux d'occupation d'une catégorie",
)
async def get_occupation(category_name: str):
    category = await category_repo.get_by_name(category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {category_name} introuvable")

    await _cleanup_expired_holds(category, category_name.upper())

    return _to_occupation(category, category_name.upper())


@router.get(
    "/occupation",
    response_model=AllCategoriesResponse,
    summary="Taux d'occupation de toutes les catégories",
)
async def get_all_occupation():
    categories = await category_repo.get_all()
    for c in categories:
        await _cleanup_expired_holds(c, c.name)

    return AllCategoriesResponse(categories=[_to_occupation(c) for c in categories])


@router.get("/categories", response_model=list[CategoryInfoResponse])
async def list_categories():
    """Liste officielle des catégories : identifiant du contrat + libellé affiché."""
    return [
        CategoryInfoResponse(category_name=name, label=label)
        for name, label in CATEGORY_LABELS.items()
    ]
