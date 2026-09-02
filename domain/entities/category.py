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
    ):
        if walkin_capacity + booking_capacity != total_capacity:
            raise ValueError(
                f"walkin_capacity ({walkin_capacity}) + booking_capacity ({booking_capacity}) "
                f"doit être égal à total_capacity ({total_capacity})"
            )

        self.name = name
        self.total_capacity = total_capacity

        self.walkin_capacity = walkin_capacity
        self.spot_taken_walkin = 0
        self.spot_available_walkin = walkin_capacity

        self.booking_capacity = booking_capacity
        self.spot_taken_booking = 0
        self.spot_available_booking = booking_capacity

        # Un seul mutex par catégorie — créé une fois, partagé par toutes les méthodes
        self._lock = asyncio.Lock()

    # GET /availability/{commercial_type}
    def is_available(self, commercial_type: CommercialType) -> bool:
        if commercial_type == CommercialType.WALKIN:
            return self.spot_available_walkin > 0
        return self.spot_available_booking > 0

    # POST /hold
    async def take(self, commercial_type: CommercialType) -> bool:
        async with self._lock:
            if not self.is_available(commercial_type):
                return False
            if commercial_type == CommercialType.WALKIN:
                self.spot_available_walkin -= 1
            else:
                self.spot_available_booking -= 1
            return True

    # POST /confirm_entry
    async def confirm_entry(self, commercial_type: CommercialType) -> None:
        async with self._lock:
            if commercial_type == CommercialType.WALKIN:
                self.spot_taken_walkin += 1
            else:
                self.spot_taken_booking += 1

    # POST /free
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

    # GET /occupation
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


# Instanciation des catégories du parking
standard   = Category(name="STANDARD",    total_capacity=70, walkin_capacity=50, booking_capacity=20)
xl         = Category(name="XL",          total_capacity=10, walkin_capacity=7,  booking_capacity=3)
electric   = Category(name="ELECTRIC",    total_capacity=15, walkin_capacity=10, booking_capacity=5)
handicap   = Category(name="HANDICAPPED", total_capacity=5,  walkin_capacity=4,  booking_capacity=1)
two_wheels = Category(name="TWO_WHEELS",  total_capacity=20, walkin_capacity=15, booking_capacity=5)
