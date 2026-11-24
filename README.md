# Micro-service Parking

Gestion du stock de places par catégorie pour le système de parking (projet fil rouge Master 2).

| | |
|---|---|
| **Version** | 1.5.0 |
| **Dernière mise à jour** | 24 novembre 2026 |
| **Production** | https://parking-6r73.onrender.com |
| **Documentation API** | https://parking-6r73.onrender.com/docs |
| **Dashboard** | https://parking-6r73.onrender.com/dashboard |

---

## État du service

| Axe | Niveau | Détail |
|---|---|---|
| Métier | Fonctionnel | Stock réel et virtuel par catégorie, holds temporaires avec expiration, mutex par catégorie, libellés d'affichage. Non exposé : modification de la répartition walk-in / booking |
| API | Fonctionnelle, documentée | 8 routes REST, Swagger sur `/docs`, erreurs 404 / 409 / 422 explicites, `/health` |
| Intégration | Première intégration réalisée | Appels REST réels avec le service Réservation. Access : workflow hold / entrée / sortie à valider en conditions réelles. RabbitMQ : non intégré à ce jour |
| UI | Fonctionnelle | Dashboard `/dashboard` : état des catégories, actions (hold, entrée, sortie), journal des résultats |
| Qualité | Tests automatisés | 43 tests : 14 unitaires sur l'entité `Category` (invariants, hold, mutex en concurrence) et 29 sur l'API (authentification, entrées invalides, cycle de vie des holds, `confirm_entry`, sortie, correlation ID), sur une base en mémoire |
| Observabilité | En cours | Logs structurés avec `X-Correlation-ID` (reçu ou généré, renvoyé dans la réponse). `/metrics` Prometheus : à faire |
| CI/CD | En place | GitHub Actions : tests à chaque push. Déploiement automatique sur Render à chaque push sur `main` |
| Sécurité | Niveau de base | Authentification par clé d'API (`X-API-Key`) sur toutes les routes `/parking/*`, validation des entrées (Pydantic), secrets en variables d'environnement. Pas d'autorisation (hors périmètre) |

---

## Sommaire

- [Prérequis](#prérequis)
- [Installation](#installation)
- [Lancement](#lancement)
- [Structure du projet](#structure-du-projet)
- [API REST](#api-rest)
- [Traçabilité et logs](#traçabilité-et-logs)
- [Dashboard](#dashboard)
- [Sécurité](#sécurité)
- [Tests et CI/CD](#tests-et-cicd)
- [Événements RabbitMQ](#événements-rabbitmq)
- [Variables d'environnement](#variables-denvironnement)
- [Règles métier](#règles-métier)

---

## Prérequis

- Python 3.12+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (optionnel)
- [Git](https://git-scm.com/)

---

## Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/BrunoZENARI/parking
cd parking
```

### 2. Créer et activer le virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Créer le dossier de base de données

```bash
mkdir db
```

---

## Lancement

### En local

```bash
# Windows PowerShell
$env:API_KEY="dev-secret-key"
uvicorn infrastructure.api.main:app --host 0.0.0.0 --port 8001 --reload
```

Le service démarre sur **http://localhost:8001**.

Sans variable `API_KEY`, la clé par défaut en local est `dev-secret-key`.

La base SQLite est créée automatiquement dans `db/parking.db` au premier démarrage, et les 5 catégories y sont initialisées. Les catégories existantes ne sont jamais modifiées : après un changement de capacité dans le code, supprimer le fichier `db/parking.db` (données de test uniquement) pour qu'il soit recréé.

### Avec Docker

```bash
docker compose up --build
```

### Sur Render

Le service est déployé automatiquement à chaque `git push` sur la branche principale. Le port est fourni par Render via `$PORT`. La base est un PostgreSQL hébergé sur Supabase, connecté par l'URL du transaction pooler (variable `DATABASE_URL`).

---

## Structure du projet

```
parking/
├── domain/                          # Cœur métier pur — aucune dépendance externe
│   ├── entities/
│   │   ├── category.py              # Entité Category + règles métier + mutex
│   │   └── temporary_hold.py        # Entité TemporaryHold + cycle de vie
│   └── ports/
│       ├── category_repository.py   # Interface (port) pour Category
│       └── temporary_hold_repository.py
│
├── application/                     # Cas d'usage
│   └── use_cases/
│
├── infrastructure/                  # Adapters
│   ├── api/
│   │   ├── main.py                  # Application FastAPI + démarrage
│   │   ├── security.py              # Authentification par clé d'API
│   │   ├── logging_config.py        # Logs + middleware de correlation ID
│   │   ├── routes/
│   │   │   └── parking_routes.py    # Routes REST + schémas Pydantic
│   │   └── static/
│   │       └── dashboard.html       # UI de démonstration et d'exploitation
│   ├── messaging/
│   │   └── consumers/
│   │       └── parking_consumer.py  # Consumer RabbitMQ (aio-pika) — non intégré
│   └── persistence/
│       └── sqlite/
│           ├── models.py                        # Modèles Tortoise ORM
│           ├── category_repository_impl.py
│           └── temporary_hold_repository_impl.py
│
├── tests/                           # Tests unitaires (pytest)
├── db/                              # Base SQLite locale (ignorée par Git)
├── .github/workflows/ci.yml         # Pipeline GitHub Actions
├── .gitignore
├── .env                             # Variables d'environnement (ne pas commiter)
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## API REST

Documentation interactive Swagger : **http://localhost:8001/docs**

Toutes les routes `/parking/*` exigent l'en-tête `X-API-Key`. `/health`, `/dashboard` et `/docs` sont accessibles sans clé.

### Capacité du parking

| Catégorie (`category_name`) | Libellé (`label`) | Total | Walk-in | Booking |
|---|---|---|---|---|
| STANDARD | Standard | 80 | 70 | 10 |
| XL | XL | 12 | 10 | 2 |
| ELECTRIC | Électrique | 12 | 12 | 0 |
| HANDICAPPED | PMR | 6 | 6 | 0 |
| TWO_WHEELS | Deux-roues | 10 | 10 | 0 |
| **Total** | | **120** | **108** | **12** |

L'identifiant `category_name` est la référence du contrat entre services. Le `label` est destiné à l'affichage (tickets, PDF, UI) : les services appelants doivent l'utiliser plutôt que de maintenir leur propre traduction.

Valeurs de `commercial_type` : `walkin` (sans réservation), `booking` (avec réservation).

### Parcours d'un véhicule

```
POST /parking/hold          → réserve une place pour 30 s, renvoie un hold_id
POST /parking/confirm_entry → valide l'entrée avec ce hold_id (stock réel)
POST /parking/free          → enregistre la sortie
```

Un hold non confirmé expire au bout de `HOLD_TIMEOUT_SECONDS` et la place est rendue au stock.

### Endpoints

#### `GET /health`
```json
{"status": "ok", "service": "parking"}
```

#### `GET /parking/availability/{category_name}/{commercial_type}`
Vérifie la disponibilité d'une catégorie.

```bash
curl -H "X-API-Key: <clé>" http://localhost:8001/parking/availability/STANDARD/walkin
```
```json
{
  "category_name": "STANDARD",
  "label": "Standard",
  "commercial_type": "walkin",
  "is_available": true,
  "spot_available": 70
}
```

#### `POST /parking/hold`
Crée un hold temporaire (retire une place du stock virtuel).

```json
{"category_name": "STANDARD", "commercial_type": "walkin"}
```
```json
{
  "hold_id": 1,
  "category_name": "STANDARD",
  "label": "Standard",
  "commercial_type": "walkin",
  "end_at": "2026-11-18T12:00:30+00:00",
  "success": true
}
```
Erreurs : `404` catégorie inconnue, `409` aucune place disponible.

#### `POST /parking/confirm_entry`
Confirme l'entrée physique du véhicule (stock réel). Le `hold_id` renvoyé par `/hold` est obligatoire.

```json
{"category_name": "STANDARD", "commercial_type": "walkin", "hold_id": 1}
```
Erreurs : `404` catégorie ou hold inconnu, `409` hold expiré, déjà utilisé, ou ne correspondant pas à la catégorie / au type, `422` champ manquant ou invalide.

#### `POST /parking/free`
Libère une place suite à une sortie.

```json
{"category_name": "STANDARD", "commercial_type": "walkin"}
```

#### `GET /parking/occupation/{category_name}`
Taux d'occupation d'une catégorie.

```json
{
  "category_name": "STANDARD",
  "label": "Standard",
  "occupation_rate": 0.25,
  "spot_taken": 20,
  "total_capacity": 80,
  "spot_held": 1
}
```

`spot_taken` : places réellement occupées. `spot_held` : places retenues par un hold actif, pas encore confirmées.

#### `GET /parking/occupation`
Taux d'occupation de toutes les catégories (même format, dans une liste `categories`).

---

## Traçabilité et logs

Chaque requête porte un identifiant de corrélation :

- si l'appelant envoie `X-Correlation-ID`, il est repris tel quel (identifiant opaque : lettres, chiffres, `.`, `_`, `-`, 64 caractères maximum, sinon un nouvel identifiant est généré) ;
- sinon, le service en génère un ;
- il apparaît dans toutes les lignes de log et est renvoyé dans l'en-tête de la réponse.

Format des logs :

```
2026-11-18 11:26:30,311 INFO [cb6ee1a1...] parking.metier: hold 23 créé (STANDARD/walkin)
2026-11-18 11:26:30,311 INFO [cb6ee1a1...] parking.http: POST /parking/hold -> 201 (28.9 ms)
```

- `parking.http` : méthode, chemin, code et durée de chaque requête (les appels répétés du dashboard et `/health` sont au niveau DEBUG)
- `parking.metier` : hold créé ou refusé, hold expiré, entrée confirmée, place libérée

Aucune donnée personnelle n'est écrite dans les logs.

---

## Dashboard

`/dashboard` permet de manipuler et d'observer le service :

- une carte par catégorie : taux d'occupation, places occupées, en attente, libres, total
- un panneau d'actions : réserver une place (hold), valider l'entrée, enregistrer la sortie
- un journal du résultat de chaque action, avec le code d'erreur et le message en cas de refus
- rafraîchissement automatique toutes les 10 secondes

---

## Sécurité

- **Authentification** : en-tête `X-API-Key` vérifié par une dépendance FastAPI appliquée à tout le router `/parking`. Clé absente ou fausse : `401`.
- **Secrets** : la clé d'API et l'URL de la base sont dans des variables d'environnement (Render en production, `.env` local ignoré par Git).
- **Validation des entrées** : schémas Pydantic, types énumérés pour `commercial_type`, catégorie vérifiée avant toute opération.
- **Erreurs** : codes HTTP explicites, sans détail interne.
- **Base de données** : Row Level Security activé sur les tables Supabase, pour fermer l'API REST publique de Supabase.
- **Dashboard** : la clé d'API n'est pas dans le code (le dépôt est public). Le dashboard la demande à l'ouverture et la garde uniquement dans la session du navigateur (`sessionStorage`). Une clé invalide est oubliée et redemandée.
- **Clé par défaut** : `dev-secret-key` n'est valable qu'en local. En production, `API_KEY` doit toujours être définie, sinon cette valeur publique s'applique.
- **Limite connue** : une clé partagée unique n'identifie pas l'appelant et n'autorise rien de précis (hors périmètre du projet : pas d'autorisation, OAuth2 ni IAM).

---

## Tests et CI/CD

```bash
pytest
```

- 14 tests unitaires sur l'entité `Category` (`tests/test_category.py`) : invariant de capacité, disponibilité, `take`, `confirm_entry`, `free`, `release_hold`, taux d'occupation, mutex en concurrence.
- 29 tests de l'API (`tests/test_api.py`), avec le client de test de FastAPI et une base SQLite en mémoire (aucune base réelle touchée, clé d'API de test définie dans `tests/conftest.py`) :
  - authentification : sans clé ou avec une mauvaise clé, `401`, sauf `/health` ;
  - entrées invalides : catégorie inconnue (`404`), type commercial invalide ou corps incomplet (`422`) ;
  - holds : stock virtuel, places en attente, refus quand il n'y a plus de place (`409`) ;
  - `confirm_entry` : hold absent, inconnu, déjà utilisé, mal assorti à la catégorie ou au type, expiré ;
  - sortie, y compris sur un parking vide ;
  - correlation ID : généré, repris s'il est valide, remplacé s'il est invalide.
- Pipeline GitHub Actions (`.github/workflows/ci.yml`) : installation et exécution des tests à chaque push.
- Déploiement : Render, automatique à chaque push sur `main`.

---

## Événements RabbitMQ

> Non intégré à ce jour. Formats à valider avec les autres micro-services (Access, Réservation). L'événement d'entrée devra transporter le `hold_id`.

Queue écoutée : **`parking.events`**

### `vehicle.entry.confirmed` (depuis Access)
```json
{"event_type": "vehicle.entry.confirmed", "category_name": "STANDARD", "commercial_type": "walkin", "hold_id": 1}
```

### `vehicle.exit.confirmed` (depuis Access)
```json
{"event_type": "vehicle.exit.confirmed", "category_name": "STANDARD", "commercial_type": "walkin"}
```

### `booking.spot.reserved` (depuis Réservation)
```json
{"event_type": "booking.spot.reserved", "category_name": "STANDARD"}
```

### `parking.repartition.update` (admin)
```json
{"event_type": "parking.repartition.update", "category_name": "STANDARD", "new_walkin_capacity": 60, "new_booking_capacity": 20}
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `API_KEY` | `dev-secret-key` | Clé attendue dans l'en-tête `X-API-Key` |
| `DATABASE_URL` | `sqlite://db/parking.db` | SQLite en local, PostgreSQL (Supabase, pooler) en production |
| `HOLD_TIMEOUT_SECONDS` | `30` | Durée d'un hold en secondes |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | URL RabbitMQ (non utilisée à ce jour) |
| `PORT` | `8001` | Port (fourni automatiquement par Render) |

---

## Règles métier

### Invariant principal
```
walkin_capacity + booking_capacity = total_capacity
```

### Stock réel vs stock virtuel
| Action | Stock virtuel | Stock réel |
|---|---|---|
| Demande de hold | -1 | inchangé |
| Confirmation entrée (hold actif obligatoire) | inchangé | +1 occupé |
| Expiration hold | +1 | inchangé |
| Sortie | +1 | -1 occupé |

### Cycle de vie d'un hold
`active` → `confirmed` (entrée validée) ou `expired` (délai dépassé). Un hold n'est utilisable qu'une seule fois.

### Mutex
Chaque catégorie possède son propre `asyncio.Lock()` : les opérations concurrentes sur une même catégorie sont sérialisées pour éviter les race conditions.

### Frontières de responsabilité
Parking ne connaît ni le véhicule, ni sa plaque, ni le paiement : il reçoit uniquement une catégorie et un type commercial. La compatibilité véhicule / place, la blacklist et la vérification de carte PMR relèvent d'Access.
