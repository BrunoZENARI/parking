import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from infrastructure.api.security import verify_api_key
from pydantic import BaseModel

from domain.entities.category import Category, CommercialType
from domain.entities.temporary_hold import HoldStatus, TemporaryHold
from infrastructure.persistence.sqlite.category_repository_impl import SQLiteCategoryRepository
from infrastructure.persistence.sqlite.temporary_hold_repository_impl import SQLiteTemporaryHoldRepository

router = APIRouter(prefix="/parking", tags=["Parking"], dependencies=[Depends(verify_api_key)])

HOLD_TIMEOUT_SECONDS = int(os.getenv("HOLD_TIMEOUT_SECONDS", 30))

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


class OccupationResponse(BaseModel):
    category_name: str
    label: str
    occupation_rate: float
    spot_taken: int
    total_capacity: int


class AllCategoriesResponse(BaseModel):
    categories: list[OccupationResponse]


# --- Helpers ---

async def _cleanup_expired_holds(category: Category, category_name: str):
    expired = await hold_repo.get_expired_active()
    for hold in expired:
        hold.status = HoldStatus.EXPIRED
        category.release_hold(hold.commercial_type)
        await hold_repo.save(hold)
    if expired:
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
    category = await category_repo.get_by_name(request.category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    await _cleanup_expired_holds(category, request.category_name.upper())

    success = await category.take(request.commercial_type)
    if not success:
        raise HTTPException(status_code=409, detail="Aucune place disponible")

    await category_repo.save(category)

    now = datetime.utcnow()
    hold = TemporaryHold(
        id=0,
        category_id=await category_repo.get_id_by_name(request.category_name.upper()),
        commercial_type=request.commercial_type,
        status=HoldStatus.ACTIVE,
        created_at=now,
        end_at=now + timedelta(seconds=HOLD_TIMEOUT_SECONDS),
    )
    saved_hold = await hold_repo.save(hold)

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
    summary="Confirmer l'entrée d'un véhicule",
)
async def confirm_entry(request: EntryExitRequest):
    category = await category_repo.get_by_name(request.category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    await category.confirm_entry(request.commercial_type)
    await category_repo.save(category)
    return {"message": "Entrée confirmée"}


@router.post(
    "/free",
    status_code=200,
    summary="Libérer une place suite à une sortie",
)
async def free_spot(request: EntryExitRequest):
    category = await category_repo.get_by_name(request.category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    await category.free(request.commercial_type)
    await category_repo.save(category)
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

    total_taken = category.spot_taken_walkin + category.spot_taken_booking
    return OccupationResponse(
        category_name=category_name.upper(),
        label=get_label(category_name),
        occupation_rate=category.occupation_rate(),
        spot_taken=total_taken,
        total_capacity=category.total_capacity,
    )


@router.get(
    "/occupation",
    response_model=AllCategoriesResponse,
    summary="Taux d'occupation de toutes les catégories",
)
async def get_all_occupation():
    categories = await category_repo.get_all()
    result = [
        OccupationResponse(
            category_name=c.name,
            label=get_label(c.name),
            occupation_rate=c.occupation_rate(),
            spot_taken=c.spot_taken_walkin + c.spot_taken_booking,
            total_capacity=c.total_capacity,
        )
        for c in categories
    ]
    return AllCategoriesResponse(categories=result)
