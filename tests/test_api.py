"""
test_api.py — Tests unitaires et d'intégration de l'API.

Tests :
  - test_health         : l'API répond correctement
  - test_version        : endpoint /version retourne la structure attendue
  - test_predictions_404: retourne 404 si aucune prédiction n'existe
  - test_predictions_ok : retourne 200 avec données insérées en DB de test
  - test_combined_404   : retourne 404 si aucune donnée combinée
  - test_combined_ok    : retourne 200 avec données insérées en DB de test

Lancer les tests :
    pytest tests/ -v
    pytest tests/ -v --tb=short
"""

import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ── Ajouter la racine du projet au path ───────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Créer une DB temporaire pour les tests (isolation complète) ───────────────
_tmp_dir = tempfile.mkdtemp()
_TEST_DB = Path(_tmp_dir) / "test_weather.db"

# Patcher la config avant d'importer l'app
import src.common.config as cfg
cfg.DB_PATH = _TEST_DB

# Importer l'app APRÈS avoir patché la config
from api.main import app
from src.common.database import init_db, insert_predictions, insert_weather_safe

import pandas as pd

# ─── Client de test ───────────────────────────────────────────────────────────
client = TestClient(app)


# ─── Fixture : DB initialisée avec données de test ────────────────────────────

@pytest.fixture(autouse=True)
def setup_db():
    """Initialise la DB de test avant chaque test."""
    init_db(_TEST_DB)
    yield
    # Nettoyage : on laisse la DB (elle est dans un dossier temporaire)


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_health():
    """L'endpoint /health doit retourner status=ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_version_structure():
    """L'endpoint /version doit retourner software_version et model_version."""
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert "software_version" in data
    assert "model_version" in data
    # En local, software_version = "0.0.0"
    assert isinstance(data["software_version"], str)
    assert isinstance(data["model_version"], str)


def test_predictions_not_found():
    """
    /predictions doit retourner 404 si aucune prédiction
    n'existe pour la date demandée.
    """
    response = client.get("/predictions?date=2099-01-01")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_predictions_ok():
    """
    /predictions doit retourner 200 avec les bonnes données
    après insertion en base.
    """
    # Insérer des prédictions de test
    target_times = [f"2025-06-01T{h:02d}:00" for h in range(0, 72, 3)]  # 24 pas
    predicted    = [27.0 + i * 0.1 for i in range(24)]

    insert_predictions(
        model_id       = "test_model",
        generated_at   = "2025-06-01T00:00",
        target_times   = target_times,
        predicted_values = predicted,
        db_path        = _TEST_DB,
    )

    response = client.get("/predictions?date=2025-06-01")
    assert response.status_code == 200

    data = response.json()
    assert data["model_id"] == "test_model"
    assert data["n_steps"]  == 24
    assert len(data["predictions"]) == 24
    # Vérifier la structure d'un enregistrement
    first = data["predictions"][0]
    assert "horizon_step" in first
    assert "target_time"  in first
    assert "predicted"    in first


def test_combined_not_found():
    """
    /predictions/combined doit retourner 404 si aucune donnée
    n'existe pour la période.
    """
    response = client.get("/predictions/combined?start=2099-01-01&end=2099-01-03")
    assert response.status_code == 404


def test_combined_ok():
    """
    /predictions/combined doit retourner 200 avec join prédictions + réel.
    """
    # Insérer des prédictions
    target_times = [f"2025-07-01T{h:02d}:00" for h in range(0, 72, 3)]
    predicted    = [28.0] * 24
    insert_predictions(
        model_id       = "test_model",
        generated_at   = "2025-07-01T00:00",
        target_times   = target_times,
        predicted_values = predicted,
        db_path        = _TEST_DB,
    )

    # Insérer des données réelles correspondantes
    df_weather = pd.DataFrame({
        "timestamp":      target_times,
        "temperature_2m": [27.5] * 24,
    })
    insert_weather_safe(df_weather, db_path=_TEST_DB)

    response = client.get("/predictions/combined?start=2025-07-01&end=2025-07-03")
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    assert "summary" in data
    assert len(data["data"]) > 0

    # Vérifier que MAE est calculé
    if data["summary"]:
        assert "mae" in data["summary"]


def test_predictions_date_format():
    """Un format de date invalide doit retourner 404 (pas de crash)."""
    response = client.get("/predictions?date=not-a-date")
    # Soit 404 (pas trouvé) soit 422 (validation) — les deux sont acceptables
    assert response.status_code in (404, 422)
