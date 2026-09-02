import asyncio

# --- Simulation SANS mutex ---

available_spots = 1  # une seule place disponible


async def create_hold_without_lock(vehicle_id: str):
    global available_spots

    print(f"[{vehicle_id}] Vérifie disponibilité : {available_spots} place(s)")

    # Simule un léger délai réseau ou base de données
    await asyncio.sleep(0.01)

    if available_spots > 0:
        available_spots -= 1
        print(f"[{vehicle_id}] ✅ Hold accordé — places restantes : {available_spots}")
    else:
        print(f"[{vehicle_id}] ❌ Aucune place disponible")


async def demo_without_lock():
    print("=== SANS MUTEX ===")
    global available_spots
    available_spots = 1

    # Deux véhicules arrivent en même temps
    await asyncio.gather(
        create_hold_without_lock("Véhicule A"),
        create_hold_without_lock("Véhicule B"),
    )
    print(f"Stock final : {available_spots} (attendu : 0, mais les deux ont eu un hold !)\n")


# --- Simulation AVEC mutex ---

available_spots_safe = 1
_lock = asyncio.Lock()  # le mutex


async def create_hold_with_lock(vehicle_id: str):
    global available_spots_safe

    print(f"[{vehicle_id}] En attente du verrou...")

    async with _lock:  # un seul à la fois entre ici
        print(f"[{vehicle_id}] Vérifie disponibilité : {available_spots_safe} place(s)")

        # Simule un léger délai réseau ou base de données
        await asyncio.sleep(0.01)

        if available_spots_safe > 0:
            available_spots_safe -= 1
            print(f"[{vehicle_id}] ✅ Hold accordé — places restantes : {available_spots_safe}")
        else:
            print(f"[{vehicle_id}] ❌ Aucune place disponible")

    print(f"[{vehicle_id}] Verrou libéré")


async def demo_with_lock():
    print("=== AVEC MUTEX ===")
    global available_spots_safe
    available_spots_safe = 1

    # Deux véhicules arrivent en même temps
    await asyncio.gather(
        create_hold_with_lock("Véhicule A"),
        create_hold_with_lock("Véhicule B"),
    )
    print(f"Stock final : {available_spots_safe} (attendu : 0 ✅)\n")


async def main():
    await demo_without_lock()
    await demo_with_lock()


if __name__ == "__main__":
    asyncio.run(main())
