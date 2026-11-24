"""
Configuration des tests de l'API.

Les variables d'environnement doivent être définies AVANT l'import de l'application :
- base SQLite en mémoire (aucun fichier, aucune base de production touchée)
- clé d'API connue des tests
"""
import os

os.environ["DATABASE_URL"] = "sqlite://:memory:"
os.environ["API_KEY"] = "test-key"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Client HTTP sur une application neuve : base vide, 5 catégories recréées au démarrage."""
    from infrastructure.api.main import app

    with TestClient(app) as c:
        yield c
