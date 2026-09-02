from domain.entities.category import CategoryName, CommercialType
from domain.ports.category_repository import CategoryRepository
from domain.ports.temporary_hold_repository import TemporaryHoldRepository


class UpdateRepartitionUseCase:

    def __init__(
        self,
        category_repo: CategoryRepository,
        hold_repo: TemporaryHoldRepository,
    ):
        self._category_repo = category_repo
        self._hold_repo = hold_repo

    async def execute(
        self,
        category_name: CategoryName,
        new_walkin_capacity: int,
        new_booking_capacity: int,
    ) -> None:
        category = await self._category_repo.get_by_name(category_name)
        if category is None:
            raise ValueError(f"Catégorie {category_name} introuvable")

        active_holds_walkin = await self._hold_repo.count_active_by_category(
            category.id, CommercialType.WALKIN
        )
        active_holds_booking = await self._hold_repo.count_active_by_category(
            category.id, CommercialType.BOOKING
        )

        category.update_repartition(
            new_walkin_capacity=new_walkin_capacity,
            new_booking_capacity=new_booking_capacity,
            active_holds_walkin=active_holds_walkin,
            active_holds_booking=active_holds_booking,
        )

        await self._category_repo.save(category)
