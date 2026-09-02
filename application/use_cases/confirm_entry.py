from domain.entities.category import CategoryName
from domain.ports.category_repository import CategoryRepository
from domain.ports.temporary_hold_repository import TemporaryHoldRepository


class ConfirmEntryUseCase:

    def __init__(
        self,
        category_repo: CategoryRepository,
        hold_repo: TemporaryHoldRepository,
    ):
        self._category_repo = category_repo
        self._hold_repo = hold_repo

    async def execute(self, hold_id: int) -> None:
        hold = await self._hold_repo.get_by_id(hold_id)
        if hold is None:
            raise ValueError(f"Hold {hold_id} introuvable")

        if hold.is_expired():
            raise ValueError(f"Hold {hold_id} expiré — entrée refusée")

        category = await self._category_repo.get_by_name(
            CategoryName(hold.category_id)
        )
        if category is None:
            raise ValueError("Catégorie introuvable")

        hold.confirm()
        category.confirm_entry(hold.commercial_type)

        await self._category_repo.save(category)
        await self._hold_repo.save_all([hold])
