from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domain.entities.category import Category, CommercialType

router = APIRouter(prefix="/parking", tags=["Parking"])

# Instanciation des catégories en mémoire — source de vérité du service
categories: dict[str, Category] = {
    "STANDARD":    Category(name="STANDARD",    total_capacity=80, walkin_capacity=70, booking_capacity=10),
    "XL":          Category(name="XL",          total_capacity=12, walkin_capacity=12, booking_capacity=0),
    "ELECTRIC":    Category(name="ELECTRIC",    total_capacity=12, walkin_capacity=12, booking_capacity=0),
    "HANDICAPPED": Category(name="HANDICAPPED", total_capacity=6,  walkin_capacity=6,  booking_capacity=0),
    "TWO_WHEELS":  Category(name="TWO_WHEELS",  total_capacity=10, walkin_capacity=10, booking_capacity=0),
}


# --- Schémas Pydantic ---

class AvailabilityResponse(BaseModel):
    category_name: str
    commercial_type: str
    is_available: bool
    spot_available: int


class HoldRequest(BaseModel):
    category_name: str
    commercial_type: CommercialType


class HoldResponse(BaseModel):
    category_name: str
    commercial_type: str
    success: bool


class FreeRequest(BaseModel):
    category_name: str
    commercial_type: CommercialType


class OccupationResponse(BaseModel):
    category_name: str
    occupation_rate: float
    spot_taken: int
    total_capacity: int


class AllCategoriesResponse(BaseModel):
    categories: list[OccupationResponse]


# --- Routes ---

@router.get(
    "/availability/{category_name}/{commercial_type}",
    response_model=AvailabilityResponse,
    summary="Vérifier la disponibilité d'une catégorie",
    description="Retourne la disponibilité pour un type de place et un mode de commercialisation.",
)
async def check_availability(category_name: str, commercial_type: CommercialType):
    category = categories.get(category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {category_name} introuvable")

    if commercial_type == CommercialType.WALKIN:
        spot_available = category.spot_available_walkin
    else:
        spot_available = category.spot_available_booking

    return AvailabilityResponse(
        category_name=category_name,
        commercial_type=commercial_type,
        is_available=category.is_available(commercial_type),
        spot_available=spot_available,
    )


@router.post(
    "/hold",
    response_model=HoldResponse,
    status_code=201,
    summary="Créer un hold temporaire sur une place",
    description="Bloque temporairement une place (stock virtuel) en attente de confirmation d'entrée.",
)
async def create_hold(request: HoldRequest):
    category = categories.get(request.category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    success = await category.take(request.commercial_type)
    if not success:
        raise HTTPException(status_code=409, detail="Aucune place disponible dans cette catégorie")

    return HoldResponse(
        category_name=request.category_name,
        commercial_type=request.commercial_type,
        success=True,
    )


@router.post(
    "/free",
    status_code=200,
    summary="Libérer une place",
    description="Libère une place suite à la sortie d'un véhicule. Incrémente stock réel et virtuel.",
)
async def free_spot(request: FreeRequest):
    category = categories.get(request.category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    await category.free(request.commercial_type)
    return {"message": "Place libérée avec succès"}


@router.post(
    "/confirm_entry",
    status_code=200,
    summary="Confirmer l'entrée d'un véhicule",
    description="Confirme l'entrée physique — décrémente le stock réel.",
)
async def confirm_entry(request: FreeRequest):
    category = categories.get(request.category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {request.category_name} introuvable")

    await category.confirm_entry(request.commercial_type)
    return {"message": "Entrée confirmée"}


@router.get(
    "/occupation/{category_name}",
    response_model=OccupationResponse,
    summary="Taux d'occupation d'une catégorie",
    description="Retourne le taux d'occupation en pourcentage pour une catégorie.",
)
async def get_occupation(category_name: str):
    category = categories.get(category_name.upper())
    if not category:
        raise HTTPException(status_code=404, detail=f"Catégorie {category_name} introuvable")

    total_taken = category.spot_taken_walkin + category.spot_taken_booking
    return OccupationResponse(
        category_name=category_name,
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
    result = []
    for name, category in categories.items():
        total_taken = category.spot_taken_walkin + category.spot_taken_booking
        result.append(OccupationResponse(
            category_name=name,
            occupation_rate=category.occupation_rate(),
            spot_taken=total_taken,
            total_capacity=category.total_capacity,
        ))
    return AllCategoriesResponse(categories=result)
