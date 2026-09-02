from dataclasses import dataclass

from domain.entities.category import CategoryName, CommercialType
from domain.ports.category_repository import CategoryRepository
from domain.ports.temporary_hold_repository import TemporaryHoldRepository


@dataclass
class CheckAvailabilityResult:
    category_name: CategoryName
    commercial_type: CommercialType
    is_available: bool
    spot_available: int


class CheckAvailabilityUseCase:

    def __init__(
        self,
        category_repo: CategoryRepository,
        hold_repo: TemporaryHoldRepository,
    ):
        self._category_repo = category_repo
        self._hold_repo = hold_repo

    async def execute(
        self, category_name: CategoryName, commercial_type: CommercialType
    ) -> CheckAvailabilityResult:
        await self._cleanup_expired_holds()

        category = await self._category_repo.get_by_name(category_name)
        if category is None:
            raise ValueError(f"Catégorie {category_name} introuvable")

        if commercial_type == CommercialType.WALKIN:
            spot_available = category.spot_available_walkin
        else:
            spot_available = category.spot_available_booking

        return CheckAvailabilityResult(
            category_name=category_name,
            commercial_type=commercial_type,
            is_available=category.is_available(commercial_type),
            spot_available=spot_available,
        )

    async def _cleanup_expired_holds(self) -> None:
        expired_holds = await self._hold_repo.get_expired_active()
        for hold in expired_holds:
            category = await self._category_repo.get_by_name(
                CategoryName(hold.category_id)
            )
            if category:
                hold.expire()
                category.release_hold(hold.commercial_type)
                await self._category_repo.save(category)
        if expired_holds:
            await self._hold_repo.save_all(expired_holds)
