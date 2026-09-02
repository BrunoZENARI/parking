from abc import ABC, abstractmethod
from typing import Optional

from domain.entities.category import CommercialType
from domain.entities.temporary_hold import TemporaryHold


class TemporaryHoldRepository(ABC):

    @abstractmethod
    async def save(self, hold: TemporaryHold) -> TemporaryHold:
        pass

    @abstractmethod
    async def get_by_id(self, hold_id: int) -> Optional[TemporaryHold]:
        pass

    @abstractmethod
    async def count_active_by_category(
        self, category_id: int, commercial_type: CommercialType
    ) -> int:
        pass

    @abstractmethod
    async def get_expired_active(self) -> list[TemporaryHold]:
        pass

    @abstractmethod
    async def save_all(self, holds: list[TemporaryHold]) -> None:
        pass
