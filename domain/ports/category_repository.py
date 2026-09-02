from abc import ABC, abstractmethod
from typing import Optional

from domain.entities.category import Category, CategoryName


class CategoryRepository(ABC):

    @abstractmethod
    async def get_by_name(self, name: CategoryName) -> Optional[Category]:
        pass

    @abstractmethod
    async def get_all(self) -> list[Category]:
        pass

    @abstractmethod
    async def save(self, category: Category) -> Category:
        pass
