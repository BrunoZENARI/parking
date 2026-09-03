from typing import Optional

from domain.entities.category import Category, CommercialType
from infrastructure.persistence.sqlite.models import CategoryModel


class SQLiteCategoryRepository:

    async def get_by_name(self, name: str) -> Optional[Category]:
        model = await CategoryModel.get_or_none(name=name)
        return self._to_domain(model) if model else None

    async def get_all(self) -> list[Category]:
        models = await CategoryModel.all()
        return [self._to_domain(m) for m in models]

    async def save(self, category: Category) -> None:
        await CategoryModel.filter(name=category.name).update(
            spot_taken_walkin=category.spot_taken_walkin,
            spot_available_walkin=category.spot_available_walkin,
            spot_taken_booking=category.spot_taken_booking,
            spot_available_booking=category.spot_available_booking,
            walkin_capacity=category.walkin_capacity,
            booking_capacity=category.booking_capacity,
        )

    async def get_or_create_all(self, categories: dict) -> None:
        for name, category in categories.items():
            await CategoryModel.get_or_create(
                name=name,
                defaults={
                    "total_capacity": category.total_capacity,
                    "walkin_capacity": category.walkin_capacity,
                    "booking_capacity": category.booking_capacity,
                    "spot_taken_walkin": category.spot_taken_walkin,
                    "spot_available_walkin": category.spot_available_walkin,
                    "spot_taken_booking": category.spot_taken_booking,
                    "spot_available_booking": category.spot_available_booking,
                }
            )

    def _to_domain(self, model: CategoryModel) -> Category:
        return Category(
            name=model.name,
            total_capacity=model.total_capacity,
            walkin_capacity=model.walkin_capacity,
            booking_capacity=model.booking_capacity,
            spot_taken_walkin=model.spot_taken_walkin,
            spot_available_walkin=model.spot_available_walkin,
            spot_taken_booking=model.spot_taken_booking,
            spot_available_booking=model.spot_available_booking,
        )

    async def get_id_by_name(self, name: str) -> int:
        model = await CategoryModel.get(name=name)
        return model.id
