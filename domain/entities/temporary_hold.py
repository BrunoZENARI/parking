from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from domain.entities.category import CommercialType


class HoldStatus(str, Enum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


@dataclass
class TemporaryHold:
    id: int
    category_id: int
    commercial_type: CommercialType
    status: HoldStatus
    created_at: datetime
    end_at: datetime

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.end_at and self.status == HoldStatus.ACTIVE

    def confirm(self) -> None:
        if self.status != HoldStatus.ACTIVE:
            raise ValueError(f"Impossible de confirmer un hold avec le statut {self.status}")
        self.status = HoldStatus.CONFIRMED

    def expire(self) -> None:
        if self.status != HoldStatus.ACTIVE:
            raise ValueError(f"Impossible d'expirer un hold avec le statut {self.status}")
        self.status = HoldStatus.EXPIRED
