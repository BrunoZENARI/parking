from domain.entities.category import CategoryName, CommercialType
from domain.ports.category_repository import CategoryRepository


class ConfirmExitUseCase:

    def __init__(self, category_repo: CategoryRepository):
        self._category_repo = category_repo

    async def execute(
        self, category_name: CategoryName, commercial_type: CommercialType
    ) -> None:
        category = await self._category_repo.get_by_name(category_name)
        if category is None:
            raise ValueError(f"Catégorie {category_name} introuvable")

        category.confirm_exit(commercial_type)
        await self._category_repo.save(category)
