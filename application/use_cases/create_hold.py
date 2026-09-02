import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from domain.entities.category import CategoryName, CommercialType
from domain.entities.temporary_hold import HoldStatus, TemporaryHold
from domain.ports.category_repository import CategoryRepository
from domain.ports.temporary_hold_repository import TemporaryHoldRepository

HOLD_TIMEOUT_SECONDS = int(os.getenv("HOLD_TIMEOUT_SECONDS", 30))


@dataclass
class CreateHoldResult:
    hold_id: int
    category_name: CategoryName
    commercial_type: CommercialType
    end_at: datetime


class CreateHoldUseCase:

    def __init__(
        self,
        category_repo: CategoryRepository,
        hold_repo: TemporaryHoldRepository,
    ):
        self._category_repo = category_repo
        self._hold_repo = hold_repo

    async def execute(
        self, category_name: CategoryName, commercial_type: CommercialType
    ) -> CreateHoldResult:
        await self._cleanup_expired_holds()

        category = await self._category_repo.get_by_name(category_name)
        if category is None:
            raise ValueError(f"Catégorie {category_name} introuvable")

        category.create_hold(commercial_type)

        now = datetime.utcnow()
        hold = TemporaryHold(
            id=0,
            category_id=category.id,
            commercial_type=commercial_type,
            status=HoldStatus.ACTIVE,
            created_at=now,
            end_at=now + timedelta(seconds=HOLD_TIMEOUT_SECONDS),
        )

        await self._category_repo.save(category)
        saved_hold = await self._hold_repo.save(hold)

        return CreateHoldResult(
            hold_id=saved_hold.id,
            category_name=category_name,
            commercial_type=commercial_type,
            end_at=saved_hold.end_at,
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
