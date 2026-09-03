from datetime import datetime
from typing import Optional

from domain.entities.category import CommercialType
from domain.entities.temporary_hold import HoldStatus, TemporaryHold
from infrastructure.persistence.sqlite.models import TemporaryHoldModel


class SQLiteTemporaryHoldRepository:

    async def save(self, hold: TemporaryHold) -> TemporaryHold:
        if hold.id == 0:
            model = await TemporaryHoldModel.create(
                category_id=hold.category_id,
                commercial_type=hold.commercial_type.value,
                status=hold.status.value,
                created_at=hold.created_at,
                end_at=hold.end_at,
            )
            hold.id = model.id
        else:
            await TemporaryHoldModel.filter(id=hold.id).update(
                status=hold.status.value,
            )
        return hold

    async def get_by_id(self, hold_id: int) -> Optional[TemporaryHold]:
        model = await TemporaryHoldModel.get_or_none(id=hold_id)
        return self._to_domain(model) if model else None

    async def get_expired_active(self) -> list[TemporaryHold]:
        models = await TemporaryHoldModel.filter(
            status=HoldStatus.ACTIVE.value,
            end_at__lt=datetime.utcnow(),
        )
        return [self._to_domain(m) for m in models]

    async def count_active_by_category(
        self, category_name: str, commercial_type: CommercialType
    ) -> int:
        category_model = await TemporaryHoldModel.filter(
            category__name=category_name,
            commercial_type=commercial_type.value,
            status=HoldStatus.ACTIVE.value,
            end_at__gt=datetime.utcnow(),
        ).count()
        return category_model

    def _to_domain(self, model: TemporaryHoldModel) -> TemporaryHold:
        return TemporaryHold(
            id=model.id,
            category_id=model.category_id,
            commercial_type=CommercialType(model.commercial_type),
            status=HoldStatus(model.status),
            created_at=model.created_at,
            end_at=model.end_at,
        )
