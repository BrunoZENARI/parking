"""
Tests de l'API REST du service Parking.

Chaque test démarre sur une base SQLite en mémoire, recréée à neuf (voir conftest.py).
"""
import pytest

HEADERS = {"X-API-Key": "test-key"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_hold(client, category="STANDARD", ctype="walkin"):
    return client.post(
        "/parking/hold",
        json={"category_name": category, "commercial_type": ctype},
        headers=HEADERS,
    )


def confirm(client, hold_id, category="STANDARD", ctype="walkin"):
    return client.post(
        "/parking/confirm_entry",
        json={"category_name": category, "commercial_type": ctype, "hold_id": hold_id},
        headers=HEADERS,
    )


def availability(client, category="STANDARD", ctype="walkin"):
    r = client.get(f"/parking/availability/{category}/{ctype}", headers=HEADERS)
    assert r.status_code == 200
    return r.json()["spot_available"]


def occupation(client, category="STANDARD"):
    r = client.get(f"/parking/occupation/{category}", headers=HEADERS)
    assert r.status_code == 200
    return r.json()


# ── Santé et authentification ─────────────────────────────────────────────────

def test_health_sans_cle_et_avec_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_route_metier_sans_cle_refusee(client):
    r = client.get("/parking/occupation")
    assert r.status_code == 401


def test_route_metier_mauvaise_cle_refusee(client):
    r = client.get("/parking/occupation", headers={"X-API-Key": "mauvaise-cle"})
    assert r.status_code == 401


# ── Entrées invalides ─────────────────────────────────────────────────────────

def test_categorie_inconnue_404(client):
    r = client.get("/parking/availability/INCONNUE/walkin", headers=HEADERS)
    assert r.status_code == 404


def test_type_commercial_invalide_422(client):
    r = client.get("/parking/availability/STANDARD/nimportequoi", headers=HEADERS)
    assert r.status_code == 422


def test_hold_corps_incomplet_422(client):
    r = client.post("/parking/hold", json={"category_name": "STANDARD"}, headers=HEADERS)
    assert r.status_code == 422


def test_hold_categorie_inconnue_404(client):
    assert make_hold(client, category="INCONNUE").status_code == 404


def test_nom_de_categorie_insensible_a_la_casse(client):
    assert client.get("/parking/availability/standard/walkin", headers=HEADERS).status_code == 200


# ── Capacités et libellés ─────────────────────────────────────────────────────

def test_capacites_initiales_xl(client):
    assert availability(client, "XL", "walkin") == 10
    assert availability(client, "XL", "booking") == 2


def test_label_pmr(client):
    body = client.get("/parking/availability/HANDICAPPED/walkin", headers=HEADERS).json()
    assert body["category_name"] == "HANDICAPPED"
    assert body["label"] == "PMR"


# ── Hold ──────────────────────────────────────────────────────────────────────

def test_hold_retire_une_place_du_stock_virtuel(client):
    avant = availability(client)
    r = make_hold(client)
    assert r.status_code == 201
    assert r.json()["label"] == "Standard"
    assert availability(client) == avant - 1


def test_hold_apparait_en_attente_dans_occupation(client):
    make_hold(client)
    occ = occupation(client)
    assert occ["spot_held"] == 1
    assert occ["spot_taken"] == 0


def test_hold_refuse_quand_plus_de_place_409(client):
    # XL : 2 places booking seulement
    assert make_hold(client, "XL", "booking").status_code == 201
    assert make_hold(client, "XL", "booking").status_code == 201
    r = make_hold(client, "XL", "booking")
    assert r.status_code == 409


def test_categorie_sans_booking_refuse_hold_booking(client):
    # ELECTRIC n'a aucune place booking
    assert make_hold(client, "ELECTRIC", "booking").status_code == 409


# ── confirm_entry : le hold est obligatoire ───────────────────────────────────

def test_confirm_entry_sans_hold_id_422(client):
    r = client.post(
        "/parking/confirm_entry",
        json={"category_name": "STANDARD", "commercial_type": "walkin"},
        headers=HEADERS,
    )
    assert r.status_code == 422


def test_confirm_entry_hold_inconnu_404(client):
    assert confirm(client, hold_id=99999).status_code == 404


def test_confirm_entry_valide_passe_en_stock_reel(client):
    hold_id = make_hold(client).json()["hold_id"]
    assert confirm(client, hold_id).status_code == 200
    occ = occupation(client)
    assert occ["spot_taken"] == 1
    assert occ["spot_held"] == 0


def test_confirm_entry_hold_deja_utilise_409(client):
    hold_id = make_hold(client).json()["hold_id"]
    assert confirm(client, hold_id).status_code == 200
    assert confirm(client, hold_id).status_code == 409
    assert occupation(client)["spot_taken"] == 1  # pas de double comptage


def test_confirm_entry_mauvaise_categorie_409(client):
    hold_id = make_hold(client, "STANDARD", "walkin").json()["hold_id"]
    assert confirm(client, hold_id, "XL", "walkin").status_code == 409


def test_confirm_entry_mauvais_type_409(client):
    hold_id = make_hold(client, "STANDARD", "walkin").json()["hold_id"]
    assert confirm(client, hold_id, "STANDARD", "booking").status_code == 409


def test_hold_expire_est_refuse_et_rend_la_place(client, monkeypatch):
    from infrastructure.api.routes import parking_routes

    avant = availability(client)
    # Durée négative : le hold est déjà expiré à sa création
    monkeypatch.setattr(parking_routes, "HOLD_TIMEOUT_SECONDS", -1)
    hold_id = make_hold(client).json()["hold_id"]

    assert confirm(client, hold_id).status_code == 409
    assert availability(client) == avant  # la place a été rendue
    assert occupation(client)["spot_held"] == 0


# ── Sortie ────────────────────────────────────────────────────────────────────

def test_sortie_libere_la_place(client):
    avant = availability(client)
    hold_id = make_hold(client).json()["hold_id"]
    confirm(client, hold_id)

    r = client.post(
        "/parking/free",
        json={"category_name": "STANDARD", "commercial_type": "walkin"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert occupation(client)["spot_taken"] == 0
    assert availability(client) == avant


def test_sortie_sur_parking_vide_ne_change_rien(client):
    avant = availability(client)
    r = client.post(
        "/parking/free",
        json={"category_name": "STANDARD", "commercial_type": "walkin"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert occupation(client)["spot_taken"] == 0
    assert availability(client) == avant


# ── Correlation ID ────────────────────────────────────────────────────────────

def test_correlation_id_genere_si_absent(client):
    r = client.get("/health")
    assert len(r.headers["X-Correlation-ID"]) >= 8


def test_correlation_id_repris_si_valide(client):
    r = client.get("/health", headers={"X-Correlation-ID": "abc-123.test_ID"})
    assert r.headers["X-Correlation-ID"] == "abc-123.test_ID"


@pytest.mark.parametrize("mauvais", ["a b", "x" * 65, "id;rm -rf", "<script>"])
def test_correlation_id_invalide_remplace(client, mauvais):
    r = client.get("/health", headers={"X-Correlation-ID": mauvais})
    assert r.headers["X-Correlation-ID"] != mauvais


# ── List Categories ────────────────────────────────────────────────────────────
def test_list_categories(client):
    r = client.get("/parking/categories", headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    names = {c["category_name"] for c in r.json()}
    assert names == {"STANDARD", "HANDICAPPED", "ELECTRIC", "XL", "TWO_WHEELS"}


def test_list_categories_requires_key(client):
    r = client.get("/parking/categories")
    assert r.status_code == 401