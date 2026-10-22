"""
Tests unitaires pour l'entité Category.
La classe Category est définie ici en standalone pour pouvoir tourner
sans l'infrastructure FastAPI/Tortoise.
"""
import asyncio
import pytest
from enum import Enum


# ── Copie standalone de l'entité (pour les tests purs) ──────────────────────

class CommercialType(str, Enum):
    WALKIN = "walkin"
    BOOKING = "booking"


class Category:

    def __init__(self, name, total_capacity, walkin_capacity, booking_capacity,
                 spot_taken_walkin=0, spot_available_walkin=None,
                 spot_taken_booking=0, spot_available_booking=None):
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

    def is_available(self, commercial_type) -> bool:
        if commercial_type == CommercialType.WALKIN:
            return self.spot_available_walkin > 0
        return self.spot_available_booking > 0

    async def take(self, commercial_type) -> bool:
        async with self._lock:
            if not self.is_available(commercial_type):
                return False
            if commercial_type == CommercialType.WALKIN:
                self.spot_available_walkin -= 1
            else:
                self.spot_available_booking -= 1
            return True

    async def confirm_entry(self, commercial_type) -> None:
        async with self._lock:
            if commercial_type == CommercialType.WALKIN:
                self.spot_taken_walkin += 1
            else:
                self.spot_taken_booking += 1

    async def free(self, commercial_type) -> None:
        async with self._lock:
            if commercial_type == CommercialType.WALKIN:
                if self.spot_taken_walkin > 0:
                    self.spot_taken_walkin -= 1
                    self.spot_available_walkin += 1
            else:
                if self.spot_taken_booking > 0:
                    self.spot_taken_booking -= 1
                    self.spot_available_booking += 1

    async def release_hold(self, commercial_type) -> None:
        async with self._lock:
            if commercial_type == CommercialType.WALKIN:
                self.spot_available_walkin += 1
            else:
                self.spot_available_booking += 1

    def occupation_rate(self) -> float:
        total_taken = self.spot_taken_walkin + self.spot_taken_booking
        return total_taken / self.total_capacity


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def standard():
    """Catégorie STANDARD avec 10 places walk-in et 5 booking."""
    return Category(
        name="STANDARD",
        total_capacity=15,
        walkin_capacity=10,
        booking_capacity=5,
    )


# ── Invariants ────────────────────────────────────────────────────────────────

def test_invariant_capacite_invalide():
    """walkin + booking != total doit lever ValueError."""
    with pytest.raises(ValueError):
        Category(name="STANDARD", total_capacity=10, walkin_capacity=6, booking_capacity=3)


def test_invariant_capacite_valide(standard):
    """walkin + booking == total doit fonctionner."""
    assert standard.walkin_capacity + standard.booking_capacity == standard.total_capacity


# ── Disponibilité ─────────────────────────────────────────────────────────────

def test_disponibilite_walkin_initiale(standard):
    """Au démarrage, toutes les places walk-in sont disponibles."""
    assert standard.is_available(CommercialType.WALKIN) is True
    assert standard.spot_available_walkin == 10


def test_disponibilite_booking_initiale(standard):
    """Au démarrage, toutes les places booking sont disponibles."""
    assert standard.is_available(CommercialType.BOOKING) is True
    assert standard.spot_available_booking == 5


# ── Hold ──────────────────────────────────────────────────────────────────────

async def test_take_walkin_decremente_stock_virtuel(standard):
    """take() décrémente le stock virtuel walk-in."""
    result = await standard.take(CommercialType.WALKIN)
    assert result is True
    assert standard.spot_available_walkin == 9


async def test_take_booking_decremente_stock_virtuel(standard):
    """take() décrémente le stock virtuel booking."""
    result = await standard.take(CommercialType.BOOKING)
    assert result is True
    assert standard.spot_available_booking == 4


async def test_take_refuse_si_plus_de_place():
    """take() retourne False si aucune place disponible."""
    c = Category(name="STANDARD", total_capacity=2, walkin_capacity=1, booking_capacity=1)
    result1 = await c.take(CommercialType.WALKIN)
    result2 = await c.take(CommercialType.WALKIN)
    assert result1 is True
    assert result2 is False
    assert c.spot_available_walkin == 0


async def test_mutex_concurrent():
    """Deux demandes simultanées pour la dernière place — une seule accordée."""
    c = Category(name="STANDARD", total_capacity=2, walkin_capacity=1, booking_capacity=1)
    results = await asyncio.gather(
        c.take(CommercialType.WALKIN),
        c.take(CommercialType.WALKIN),
    )
    assert results.count(True) == 1
    assert results.count(False) == 1
    assert c.spot_available_walkin == 0


# ── Confirm entry ─────────────────────────────────────────────────────────────

async def test_confirm_entry_decremente_stock_reel(standard):
    """confirm_entry() décrémente le stock réel (spot_taken)."""
    await standard.take(CommercialType.WALKIN)
    await standard.confirm_entry(CommercialType.WALKIN)
    assert standard.spot_taken_walkin == 1
    assert standard.spot_available_walkin == 9


# ── Free ──────────────────────────────────────────────────────────────────────

async def test_free_libere_stock_reel_et_virtuel(standard):
    """free() libère stock réel ET stock virtuel."""
    await standard.take(CommercialType.WALKIN)
    await standard.confirm_entry(CommercialType.WALKIN)
    await standard.free(CommercialType.WALKIN)
    assert standard.spot_taken_walkin == 0
    assert standard.spot_available_walkin == 10


async def test_free_sans_place_occupee_ne_plante_pas(standard):
    """free() sur une catégorie déjà vide ne plante pas."""
    await standard.free(CommercialType.WALKIN)
    assert standard.spot_taken_walkin == 0
    assert standard.spot_available_walkin == 10


# ── Taux d'occupation ─────────────────────────────────────────────────────────

def test_taux_occupation_vide(standard):
    """Taux d'occupation à 0.0 au démarrage."""
    assert standard.occupation_rate() == 0.0


async def test_taux_occupation_apres_entree(standard):
    """Taux d'occupation = 1/total après une entrée confirmée."""
    await standard.take(CommercialType.WALKIN)
    await standard.confirm_entry(CommercialType.WALKIN)
    assert standard.occupation_rate() == pytest.approx(1 / 15)


# ── Release hold ──────────────────────────────────────────────────────────────

async def test_release_hold_remet_place_disponible(standard):
    """release_hold() restitue la place dans le stock virtuel."""
    await standard.take(CommercialType.WALKIN)
    assert standard.spot_available_walkin == 9
    await standard.release_hold(CommercialType.WALKIN)
    assert standard.spot_available_walkin == 10
