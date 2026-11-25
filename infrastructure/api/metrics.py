from prometheus_client import Counter, Gauge, Histogram

# --- Métriques techniques ---
HTTP_REQUESTS = Counter(
        "http_requests_total", "Requêtes HTTP reçues", ["method", "path", "status"]
)
HTTP_DURATION = Histogram(
    "parking_http_request_duration_seconds", "Durée des requêtes HTTP", ["method", "path"]
)
OPERATIONS = Counter(
    "parking_operations_total",
    "Opérations métier du parking",
    ["operation", "category", "commercial_type", "result"],
)

# --- Métriques métier (compteurs) ---
_LABELS = ["category", "commercial_type"]
HOLDS_CREATED = Counter("parking_holds_created_total", "Holds créés", _LABELS)
HOLDS_REFUSED = Counter("parking_holds_refused_total", "Holds refusés (plus de place)", _LABELS)
HOLDS_EXPIRED = Counter("parking_holds_expired_total", "Holds expirés (place rendue)", _LABELS)
ENTRIES_CONFIRMED = Counter("parking_entries_confirmed_total", "Entrées confirmées", _LABELS)
ENTRIES_REFUSED = Counter("parking_entries_refused_total", "Entrées refusées (capacité atteinte)", _LABELS)
EXITS = Counter("parking_exits_total", "Sorties (places libérées)", _LABELS)

# --- Métriques métier (état du stock) ---
SPOTS_TAKEN = Gauge("parking_spots_taken", "Places occupées", _LABELS)
SPOTS_HELD = Gauge("parking_spots_held", "Places en attente (holds actifs)", _LABELS)
SPOTS_AVAILABLE = Gauge("parking_spots_available", "Places disponibles", _LABELS)


def update_stock_gauges(c) -> None:
    """Met à jour les jauges de stock à partir d'une catégorie."""
    for ctype, capacity, taken, available in (
        ("walkin", c.walkin_capacity, c.spot_taken_walkin, c.spot_available_walkin),
        ("booking", c.booking_capacity, c.spot_taken_booking, c.spot_available_booking),
    ):
        SPOTS_TAKEN.labels(c.name, ctype).set(taken)
        SPOTS_HELD.labels(c.name, ctype).set(max(0, capacity - taken - available))
        SPOTS_AVAILABLE.labels(c.name, ctype).set(available)