# Journal de développement — Micro-service Parking

## 02 septembre 2026

---

## 1. Cadrage du projet

Projet fil rouge Master 2 — système de gestion d'un parking découpé en 7 micro-services, chaque étudiant responsable d'un service :

- **Véhicules** — plaque, type, propriétaire, statut
- **Parking** — places, zones, capacité, occupation ← Bruno
- **Réservation** — créneaux, expiration, conflits
- **Accès** — entrée/sortie, plaque connue/inconnue, autorisation
- **Tarification** — durée, forfait, gratuité, règles tarifaires
- **Paiement** — paiement, statut, refus, remboursement, idempotence
- **Notification** — événements, destinataires, retry, canal

Communication inter-services : **API REST** (synchrone) + **RabbitMQ** (asynchrone).

---

## 2. Réflexion sur les règles métier

### 2.1 Modélisation des entités

**Décision clé** : les places sont gérées par **nombre disponible par catégorie**, pas nominalement (pas de table `Place` avec un identifiant par place physique pour le MVP).

Entité centrale : `Category` — un compteur par type de place.

**Catégories définies :**

| Catégorie | Total | Walk-in | Booking |
|---|---|---|---|
| STANDARD | 80 | 70 | 10 |
| XL | 12 | 12 | 0 |
| ELECTRIC | 12 | 12 | 0 |
| HANDICAPPED | 6 | 6 | 0 |
| TWO_WHEELS | 10 | 10 | 0 |
| **Total** | **120** | **110** | **10** |

**Attributs de `Category` :**
- `name` — nom de la catégorie
- `total_capacity` — capacité totale fixe
- `walkin_capacity` — places allouées au walk-in
- `booking_capacity` — places allouées au booking
- `spot_taken_walkin` — stock réel walk-in (places confirmées occupées)
- `spot_available_walkin` — stock virtuel walk-in (tient compte des holds)
- `spot_taken_booking` — stock réel booking
- `spot_available_booking` — stock virtuel booking

**Invariant principal :**
```
walkin_capacity + booking_capacity = total_capacity  →  toujours vrai
```

### 2.2 Mécanisme de hold temporaire

Pour éviter les race conditions lors des entrées simultanées, mise en place d'un **stock réel vs stock virtuel** :

| Action | Stock virtuel (`spot_available_*`) | Stock réel (`spot_taken_*`) |
|---|---|---|
| Demande de hold | -1 | inchangé |
| Confirmation entrée | inchangé | -1 |
| Expiration hold | +1 | inchangé |
| Sortie | +1 | +1 |

Entité `TemporaryHold` :
- `id`
- `category_id` — FK vers Category
- `commercial_type` — walkin ou booking
- `status` — active, confirmed, expired
- `created_at`
- `end_at` — moment d'expiration (30 secondes par défaut)

Le service gère lui-même l'expiration des holds (lazy cleanup à chaque requête).

### 2.3 Règles métier de modification de répartition

Lors d'une modification de `walkin_capacity` / `booking_capacity`, la contrainte à valider :
```
new_walkin_capacity >= spot_taken_walkin + holds_actifs_walkin
new_booking_capacity >= spot_taken_booking + holds_actifs_booking
```
On ne peut pas réduire une capacité en dessous du nombre de places déjà engagées (occupées + holds en cours).

### 2.4 Mutex

Chaque `Category` possède son propre `asyncio.Lock()` pour sérialiser les opérations concurrentes et éviter les race conditions sur le stock.

```python
async with self._lock:
    if not self.is_available(commercial_type):
        return False
    self.spot_available_walkin -= 1
    return True
```

### 2.5 Frontières de responsabilité

- **Blacklist mauvais payeur** → appartient à Paiement et Accès, pas à Parking
- **Vérification carte handicapé** → contrôle externe (ANTS), Parking ne stocke pas de données de santé (RGPD)
- **Règles de compatibilité véhicule/place** → appartient à Accès (un 2 roues peut prendre une place 4 roues, etc.)
- **Stationnement en cours** → appartient à Accès
- Parking reçoit uniquement un `category_name` et un `commercial_type` — il ne connaît pas le véhicule

---

## 3. Architecture et flux inter-services

### Rôle de Parking dans le flux global

Parking est un service **passif** — il répond aux demandes, n'initie rien.

**Appels synchrones REST (réponse immédiate nécessaire) :**
- Access → Parking : disponibilité d'une place
- Access → Parking : création d'un hold

**Événements asynchrones RabbitMQ (faits accomplis) :**
- Access → Parking : confirmation d'entrée
- Access → Parking : confirmation de sortie
- Booking → Parking : réservation confirmée (décrémente stock booking)

### Flux entrée/sortie

**Entrée :**
1. Access appelle `GET /parking/availability/{category}/{commercial_type}`
2. Access appelle `POST /parking/hold` → reçoit un `hold_id`
3. Barrière s'ouvre
4. Access publie `vehicle.entry.confirmed` → Parking confirme l'entrée en base

**Sortie :**
1. Access publie `vehicle.exit.confirmed` → Parking libère la place

---

## 4. Code — Classe `Category`

Basée sur le modèle fourni par le professeur, corrigé et étendu :

```python
class Category:
    def __init__(self, name, total_capacity, walkin_capacity, booking_capacity, ...):
        # Invariant vérifié à l'instanciation
        if walkin_capacity + booking_capacity != total_capacity:
            raise ValueError(...)
        self._lock = asyncio.Lock()  # Un mutex par catégorie

    async def take(self, commercial_type) -> bool: ...      # Décrémente stock virtuel
    async def confirm_entry(self, commercial_type): ...     # Décrémente stock réel
    async def free(self, commercial_type): ...              # Libère stock réel + virtuel
    async def release_hold(self, commercial_type): ...      # Libère hold expiré
    def occupation_rate(self) -> float: ...                 # taken / total
```

---

## 5. Stack technique

- **Langage** : Python 3.12
- **Framework** : FastAPI + Uvicorn
- **ORM** : Tortoise ORM (async natif)
- **Base de données** : PostgreSQL (Render) / SQLite (local)
- **Driver PostgreSQL** : asyncpg
- **Messagerie** : RabbitMQ via aio-pika (à intégrer)
- **Documentation** : Swagger auto-généré par FastAPI (`/docs`)
- **Architecture** : Hexagonale (Domain / Application / Infrastructure)
- **Déploiement** : Docker + Render + Git

---

## 6. API REST exposée

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | Santé du service |
| GET | `/parking/availability/{category}/{commercial_type}` | Disponibilité |
| POST | `/parking/hold` | Créer un hold temporaire |
| POST | `/parking/confirm_entry` | Confirmer l'entrée |
| POST | `/parking/free` | Libérer une place |
| GET | `/parking/occupation/{category}` | Taux d'occupation |
| GET | `/parking/occupation` | Taux d'occupation global |

---


## 03 septembre 2026

## 7. Mise en place de la base de données

**Étape 1 — SQLite en local**
- Ajout de `tortoise-orm` et `aiosqlite` dans `requirements.txt`
- Création des modèles Tortoise ORM : `CategoryModel` et `TemporaryHoldModel`
- Création des repositories SQLite
- Initialisation automatique des tables via `generate_schemas=True`
- Initialisation automatique des 5 catégories via `get_or_create_all()` au startup

**Étape 2 — Migration vers PostgreSQL sur Render**

SQLite est un fichier local détruit à chaque redéploiement — migration vers PostgreSQL pour persistance en ligne.

- Création d'une base PostgreSQL sur Render (`parking-db`, plan Free, région Frankfurt)
- Ajout de `asyncpg` dans `requirements.txt`
- Ajout de la variable `DATABASE_URL` dans le service Render (Internal URL)
- `.env` local avec External URL (non commité — dans `.gitignore`)

---

## 8. Corrections et bugs

### Bug — `category_id` invalide dans `TemporaryHold`

**Symptôme :**
```
ValueError: invalid literal for int() with base 10: 'STANDARD'
```

**Cause :** On passait le nom `"STANDARD"` au lieu de l'id entier à la FK `category_id`.

**Correction :**
- Ajout de `get_id_by_name()` dans `SQLiteCategoryRepository`
- Modification de `create_hold` pour récupérer l'id réel avant création du hold

---

## 9. Historique des commits Git

| Commit | Description |
|---|---|
| `feat: micro-service parking initial` | Structure hexagonale, routes FastAPI, Swagger |
| `fix: port dynamique pour Render` | `${PORT:-8001}` dans le Dockerfile |
| `feat: persistance SQLite + README mis à jour` | Tortoise ORM, modèles, repositories, BDD |
| `feat: ajout asyncpg pour PostgreSQL` | Migration SQLite → PostgreSQL |
| `fix: category_id entier au lieu du nom pour TemporaryHold` | Correction bug FK |

---

## 10. Service en production

- **URL** : `https://parking-6r73.onrender.com`
- **Swagger** : `https://parking-6r73.onrender.com/docs`
- **Health** : `https://parking-6r73.onrender.com/health`
- **Base de données** : PostgreSQL sur Render (Frankfurt)

---

## 11. Interface avec le micro-service Access

**Entrée :**
```
GET  /parking/availability/{category_name}/{commercial_type}
POST /parking/hold          → {"category_name": "STANDARD", "commercial_type": "walkin"}
POST /parking/confirm_entry → {"category_name": "STANDARD", "commercial_type": "walkin"}
```

**Sortie :**
```
POST /parking/free → {"category_name": "STANDARD", "commercial_type": "walkin"}
```

---

## 12. Points en suspens

- Intégration RabbitMQ (consumer) — à faire après coordination avec Access et Booking
- Format des messages RabbitMQ à valider avec le groupe
- Endpoint admin pour modification de répartition walk-in / booking
