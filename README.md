# Micro-service Parking

Gestion du stock de places par catégorie pour le système de parking.

---

## Sommaire

- [Prérequis](#prérequis)
- [Installation](#installation)
- [Lancement](#lancement)
- [Structure du projet](#structure-du-projet)
- [API REST](#api-rest)
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
uvicorn infrastructure.api.main:app --host 0.0.0.0 --port 8001 --reload
```

Le service démarre sur **http://localhost:8001**

La base de données SQLite est créée automatiquement dans `db/parking.db` au premier démarrage.
Les 5 catégories sont initialisées en base si elles n'existent pas encore.

### Avec Docker

```bash
docker compose up --build
```

### Sur Render

Le service est déployé automatiquement à chaque `git push` sur la branche principale.
Le port est fourni dynamiquement par Render via la variable `$PORT`.

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
│       ├── check_availability.py
│       ├── create_hold.py
│       ├── confirm_entry.py
│       ├── confirm_exit.py
│       └── update_repartition.py
│
├── infrastructure/                  # Adapters
│   ├── api/
│   │   ├── main.py                  # Application FastAPI + démarrage
│   │   └── routes/
│   │       └── parking_routes.py    # Routes REST + schémas Pydantic
│   ├── messaging/
│   │   └── consumers/
│   │       └── parking_consumer.py  # Consumer RabbitMQ (aio-pika)
│   └── persistence/
│       └── sqlite/
│           ├── models.py                        # Modèles Tortoise ORM
│           ├── category_repository_impl.py      # Implémentation SQLite
│           └── temporary_hold_repository_impl.py
│
├── db/                              # Base de données SQLite (créée automatiquement)
├── .gitignore
├── .env                             # Variables d'environnement (ne pas commiter)
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## API REST

Documentation interactive Swagger : **http://localhost:8001/docs**

### Capacité du parking

| Catégorie | Total | Walk-in | Booking |
|---|---|---|---|
| STANDARD | 80 | 70 | 10 |
| XL | 12 | 12 | 0 |
| ELECTRIC | 12 | 12 | 0 |
| HANDICAPPED | 6 | 6 | 0 |
| TWO_WHEELS | 10 | 10 | 0 |
| **Total** | **120** | **110** | **10** |

### Endpoints

#### `GET /health`
```json
{"status": "ok", "service": "parking"}
```

#### `GET /parking/availability/{category_name}/{commercial_type}`
Vérifie la disponibilité d'une catégorie.

Valeurs `category_name` : `STANDARD`, `XL`, `ELECTRIC`, `HANDICAPPED`, `TWO_WHEELS`
Valeurs `commercial_type` : `walkin`, `booking`

```bash
curl http://localhost:8001/parking/availability/STANDARD/walkin
```
```json
{
  "category_name": "STANDARD",
  "commercial_type": "walkin",
  "is_available": true,
  "spot_available": 70
}
```

#### `POST /parking/hold`
Crée un hold temporaire (bloque le stock virtuel).

```json
{"category_name": "STANDARD", "commercial_type": "walkin"}
```
```json
{
  "hold_id": 1,
  "category_name": "STANDARD",
  "commercial_type": "walkin",
  "end_at": "2025-01-01T12:00:30",
  "success": true
}
```

#### `POST /parking/confirm_entry`
Confirme l'entrée physique du véhicule (décrémente le stock réel).

```json
{"category_name": "STANDARD", "commercial_type": "walkin"}
```

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
  "occupation_rate": 0.25,
  "spot_taken": 20,
  "total_capacity": 80
}
```

#### `GET /parking/occupation`
Taux d'occupation de toutes les catégories.

---

## Événements RabbitMQ

> ⚠️ Formats à valider avec les autres micro-services (Access, Booking).

Queue écoutée : **`parking.events`**

### `vehicle.entry.confirmed` (depuis Access)
```json
{"event_type": "vehicle.entry.confirmed", "category_name": "STANDARD", "commercial_type": "walkin"}
```

### `vehicle.exit.confirmed` (depuis Access)
```json
{"event_type": "vehicle.exit.confirmed", "category_name": "STANDARD", "commercial_type": "walkin"}
```

### `booking.spot.reserved` (depuis Booking)
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
| `DATABASE_URL` | `sqlite://db/parking.db` | Chemin SQLite |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | URL RabbitMQ |
| `HOLD_TIMEOUT_SECONDS` | `30` | Durée du hold en secondes |
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
| Confirmation entrée | inchangé | -1 |
| Expiration hold | +1 | inchangé |
| Sortie | +1 | +1 |

### Mutex
Chaque catégorie possède son propre `asyncio.Lock()` — les opérations concurrentes sur une même catégorie sont sérialisées pour éviter les race conditions.
