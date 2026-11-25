from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, disable_created_metrics

# Supprime les séries "*_created" (horodatage de création), inutiles pour la supervision.
# Doit être appelé avant la création des métriques.
disable_created_metrics()

# Registre dédié : seules nos métriques sont exposées
# (pas de python_gc_*, process_* ni python_info du registre par défaut).
REGISTRY = CollectorRegistry()

# --- Métriques techniques ---
HTTP_REQUESTS = Counter(
    "http_requests_total", "Requêtes HTTP reçues", ["method", "path", "status"],
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds", "Durée des requêtes HTTP", ["method", "path"],
    registry=REGISTRY,
)
OPERATIONS = Counter(
    "parking_operations_total",
    "Opérations métier du parking",
    ["operation", "category", "commercial_type", "result"],
    registry=REGISTRY,
)

# --- Métriques métier (compteurs) ---
_LABELS = ["category", "commercial_type"]
HOLDS_CREATED = Counter("parking_holds_created_total", "Holds créés", _LABELS, registry=REGISTRY)
HOLDS_REFUSED = Counter("parking_holds_refused_total", "Holds refusés (plus de place)", _LABELS, registry=REGISTRY)
HOLDS_EXPIRED = Counter("parking_holds_expired_total", "Holds expirés (place rendue)", _LABELS, registry=REGISTRY)
ENTRIES_CONFIRMED = Counter("parking_entries_confirmed_total", "Entrées confirmées", _LABELS, registry=REGISTRY)
ENTRIES_REFUSED = Counter("parking_entries_refused_total", "Entrées refusées (capacité atteinte)", _LABELS, registry=REGISTRY)
EXITS = Counter("parking_exits_total", "Sorties (places libérées)", _LABELS, registry=REGISTRY)

# --- Métriques métier (état du stock) ---
SPOTS_TAKEN = Gauge("parking_spots_taken", "Places occupées", _LABELS, registry=REGISTRY)
SPOTS_HELD = Gauge("parking_spots_held", "Places en attente (holds actifs)", _LABELS, registry=REGISTRY)
SPOTS_AVAILABLE = Gauge("parking_spots_available", "Places disponibles", _LABELS, registry=REGISTRY)
VEHICLES_PARKED = Gauge("parking_vehicles_parked", "Total des véhicules actuellement garés", registry=REGISTRY)
OCCUPATION_RATE = Gauge("parking_occupation_rate", "Taux d'occupation (0 à 1)", ["category"], registry=REGISTRY)


def update_stock_gauges(c) -> None:
    """Met à jour les jauges de stock à partir d'une catégorie."""
    for ctype, capacity, taken, available in (
        ("walkin", c.walkin_capacity, c.spot_taken_walkin, c.spot_available_walkin),
        ("booking", c.booking_capacity, c.spot_taken_booking, c.spot_available_booking),
    ):
        SPOTS_TAKEN.labels(c.name, ctype).set(taken)
        SPOTS_HELD.labels(c.name, ctype).set(max(0, capacity - taken - available))
        SPOTS_AVAILABLE.labels(c.name, ctype).set(available)
    OCCUPATION_RATE.labels(c.name).set(c.occupation_rate())
