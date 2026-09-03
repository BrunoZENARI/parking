import asyncio
from enum import Enum


class CommercialType(str, Enum):
    WALKIN = "walkin"
    BOOKING = "booking"


class Category:

    def __init__(
        self,
        name: str,
        total_capacity: int,
        walkin_capacity: int,
        booking_capacity: int,
        spot_taken_walkin: int = 0,
        spot_available_walkin: int = None,
        spot_taken_booking: int = 0,
        spot_available_booking: int = None,
    ):
        if walkin_capacity + booking_capacity != total_capacity:
            raise ValueError(
                f"walkin_capacity ({walkin_capacity}) + booking_capacity ({booking_capacity}) "
                f"doit être égal à total_capacity ({total_capacity})"
            )

        self.name = name
        self.total_capacity = total_capacity

        self.walkin_capacity = walkin_capacity
        self.spot_taken_walkin = spot_taken_walkin
        self.spot_available_walkin = spot_available_walkin if spot_available_walkin is not None else walkin_capacity

        self.booking_capacity = booking_capacity
        self.spot_taken_booking = spot_taken_booking
        self.spot_available_booking = spot_available_booking if spot_available_booking is not None else booking_capacity

        self._lock = asyncio.Lock()

    def is_available(self, commercial_type: CommercialType) -> bool:
        if commercial_type == CommercialType.WALKIN:
            return self.spot_available_walkin > 0
        return self.spot_available_booking > 0

    async def take(self, commercial_type: CommercialType) -> bool:
        async with self._lock:
            if not self.is_available(commercial_type):
                return False
            if commercial_type == CommercialType.WALKIN:
                self.spot_available_walkin -= 1
            else:
                self.spot_available_booking -= 1
            return True

    async def confirm_entry(self, commercial_type: CommercialType) -> None:
        async with self._lock:
            if commercial_type == CommercialType.WALKIN:
                self.spot_taken_walkin += 1
            else:
                self.spot_taken_booking += 1

    async def free(self, commercial_type: CommercialType) -> None:
        async with self._lock:
            if commercial_type == CommercialType.WALKIN:
                if self.spot_taken_walkin > 0:
                    self.spot_taken_walkin -= 1
                    self.spot_available_walkin += 1
            else:
                if self.spot_taken_booking > 0:
                    self.spot_taken_booking -= 1
                    self.spot_available_booking += 1

    async def release_hold(self, commercial_type: CommercialType) -> None:
        async with self._lock:
            if commercial_type == CommercialType.WALKIN:
                self.spot_available_walkin += 1
            else:
                self.spot_available_booking += 1

    def occupation_rate(self) -> float:
        total_taken = self.spot_taken_walkin + self.spot_taken_booking
        return total_taken / self.total_capacity

    def __repr__(self) -> str:
        return (
            f"Category({self.name}) "
            f"walkin={self.spot_taken_walkin}/{self.walkin_capacity} "
            f"booking={self.spot_taken_booking}/{self.booking_capacity} "
            f"occupation={self.occupation_rate():.0%}"
        )
