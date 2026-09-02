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

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et lancé
- [Git](https://git-scm.com/) (optionnel, pour cloner)
- Python 3.12+ (uniquement si tu veux lancer sans Docker)

---

## Installation

### 1. Cloner ou dézipper le projet

```bash
# Si tu as Git
git clone <url-du-repo>
cd parking

# Sinon, dézippé le fichier parking.zip et ouvre un terminal dans le dossier
cd parking
```

### 2. Vérifier le fichier .env

Le fichier `.env` est déjà présent avec les valeurs par défaut :

```env
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
DATABASE_URL=sqlite://db/parking.db
HOLD_TIMEOUT_SECONDS=30
```

Tu peux modifier `HOLD_TIMEOUT_SECONDS` pour ajuster le délai du hold temporaire.

---

## Lancement

### Avec Docker (recommandé)

```bash
# Construire et démarrer les conteneurs
docker compose up --build

# En arrière-plan
docker compose up --build -d

# Voir les logs
docker compose logs -f parking

# Arrêter
docker compose down
```

Le service démarre sur **http://localhost:8001**

RabbitMQ démarre sur :
- **http://localhost:15672** — interface web (login : guest / guest)
- **port 5672** — port AMQP utilisé par les services

### Sans Docker (développement local)

```bash
# Créer un environnement virtuel
python -m venv venv

# Activer l'environnement virtuel
# Sur Mac/Linux :
source venv/bin/activate
# Sur Windows :
venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Créer le dossier de la base de données
mkdir -p db

# Lancer le service
uvicorn infrastructure.api.main:app --host 0.0.0.0 --port 8001 --reload
```

> ⚠️ Sans Docker, RabbitMQ ne sera pas disponible. Le service démarrera quand même mais le consumer RabbitMQ sera inactif.

---

## Structure du projet

```
parking/
├── domain/                          # Cœur métier pur — aucune dépendance externe
│   ├── entities/
│   │   ├── category.py              # Entité Category + règles métier
│   │   └── temporary_hold.py        # Entité TemporaryHold + cycle de vie
│   └── ports/
│       ├── category_repository.py   # Interface (port) pour Category
│       └── temporary_hold_repository.py  # Interface (port) pour TemporaryHold
│
├── application/                     # Cas d'usage — orchestre le domain
│   └── use_cases/
│       ├── check_availability.py    # Vérifier disponibilité d'une catégorie
│       ├── create_hold.py           # Créer un hold temporaire
│       ├── confirm_entry.py         # Confirmer l'entrée d'un véhicule
│       ├── confirm_exit.py          # Confirmer la sortie d'un véhicule
│       └── update_repartition.py    # Modifier répartition walkin/booking
│
├── infrastructure/                  # Adapters — implémentations concrètes
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
├── db/                              # Fichier SQLite (créé automatiquement)
├── .env                             # Variables d'environnement
├── requirements.txt                 # Dépendances Python
├── Dockerfile                       # Image Docker du service
└── docker-compose.yml               # Orchestration Docker
```

---

## API REST

La documentation interactive Swagger est disponible sur :

**http://localhost:8001/docs**

### Endpoints

#### `GET /health`
Vérifie que le service est opérationnel.

**Réponse :**
```json
{
  "status": "ok",
  "service": "parking"
}
```

---

#### `GET /parking/availability/{category_name}/{commercial_type}`
Vérifie la disponibilité d'une catégorie pour un mode de commercialisation.

**Paramètres :**
| Paramètre | Type | Valeurs possibles |
|---|---|---|
| `category_name` | string | `STANDARD`, `XL`, `HANDICAPPED`, `ELECTRIC`, `TWO_WHEELS` |
| `commercial_type` | string | `walkin`, `booking` |

**Exemple :**
```bash
curl http://localhost:8001/parking/availability/STANDARD/walkin
```

**Réponse 200 :**
```json
{
  "category_name": "STANDARD",
  "commercial_type": "walkin",
  "is_available": true,
  "spot_available": 5
}
```

**Réponse 404 :** Catégorie introuvable.

---

#### `POST /parking/hold`
Crée un hold temporaire sur une place (bloque le stock virtuel).

**Corps de la requête :**
```json
{
  "category_name": "STANDARD",
  "commercial_type": "walkin"
}
```

**Exemple :**
```bash
curl -X POST http://localhost:8001/parking/hold \
  -H "Content-Type: application/json" \
  -d '{"category_name": "STANDARD", "commercial_type": "walkin"}'
```

**Réponse 201 :**
```json
{
  "hold_id": 1,
  "category_name": "STANDARD",
  "commercial_type": "walkin",
  "end_at": "2025-01-01T12:00:30"
}
```

**Réponse 409 :** Aucune place disponible.

---

## Événements RabbitMQ

Le service écoute la queue **`parking.events`**.

> ⚠️ **À coordonner avec les autres services** — ces formats sont à valider avec Access et Booking.

### Événements consommés

#### `vehicle.entry.confirmed`
Publié par **Access** quand un véhicule a physiquement franchi la barrière.

```json
{
  "event_type": "vehicle.entry.confirmed",
  "hold_id": 1
}
```

➡️ Confirme le hold, décrémente le stock réel.

---

#### `vehicle.exit.confirmed`
Publié par **Access** quand un véhicule est sorti.

```json
{
  "event_type": "vehicle.exit.confirmed",
  "category_name": "STANDARD",
  "commercial_type": "walkin"
}
```

➡️ Libère la place, incrémente stock réel et virtuel.

---

#### `parking.repartition.update`
Publié par un **administrateur** (via Access ou une interface admin) pour modifier la répartition.

```json
{
  "event_type": "parking.repartition.update",
  "category_name": "STANDARD",
  "new_walkin_capacity": 8,
  "new_booking_capacity": 2
}
```

➡️ Recalcule la répartition en respectant les contraintes métier.

---

#### `booking.spot.reserved`
Publié par **Booking** quand une réservation est confirmée.

```json
{
  "event_type": "booking.spot.reserved",
  "category_name": "STANDARD"
}
```

➡️ Décrémente le stock booking disponible.

---

## Variables d'environnement

| Variable | Valeur par défaut | Description |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | URL de connexion RabbitMQ |
| `DATABASE_URL` | `sqlite://db/parking.db` | Chemin de la base SQLite |
| `HOLD_TIMEOUT_SECONDS` | `30` | Durée du hold temporaire en secondes |

---

## Règles métier

### Invariants de la Category
- `walkin_capacity + booking_capacity = total_capacity` — toujours vrai
- `spot_available_walkin <= walkin_capacity` — toujours vrai
- `spot_available_booking <= booking_capacity` — toujours vrai

### Stock réel vs stock virtuel
- **Stock virtuel** (`spot_available_*`) : décrémenté à la création d'un hold
- **Stock réel** (`spot_taken_*`) : décrémenté à la confirmation d'entrée
- La disponibilité est toujours calculée sur le stock virtuel

### Modification de répartition
La nouvelle capacité demandée doit satisfaire :
```
new_walkin_capacity >= spot_taken_walkin + holds_actifs_walkin
new_booking_capacity >= spot_taken_booking + holds_actifs_booking
```

### Catégories disponibles
| Nom | Description |
|---|---|
| `STANDARD` | Place voiture standard |
| `XL` | Place grande taille |
| `HANDICAPPED` | Place handicapé |
| `ELECTRIC` | Place avec borne de recharge |
| `TWO_WHEELS` | Place 2 roues |
