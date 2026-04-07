"""
test_api.py — Tests unitaires et d'intégration de l'API.

Tests :
  - test_health                   : l'API répond correctement
  - test_version_structure        : endpoint /version retourne la structure attendue
  - test_predictions_not_found    : retourne 404 si aucune prédiction n'existe
  - test_predictions_ok           : retourne 200 avec données insérées en DB de test
  - test_combined_not_found       : retourne 404 si aucune donnée combinée
  - test_combined_ok              : retourne 200 avec données insérées en DB de test
  - test_predictions_date_format  : date invalide → 404 ou 422
  - test_monitoring_data_empty    : /monitoring/data → rows vide si aucune donnée
  - test_monitoring_data_with_rows: /monitoring/data → structure correcte avec données
  - test_monitoring_data_days_param: paramètre days validé (1–90)
  - test_monitoring_refresh_no_data: /monitoring/refresh → status no_data si DB vide
  - test_monitoring_refresh_ok    : /monitoring/refresh → MAE/RMSE/biais calculés
  - test_pipeline_fetch_ok        : POST /pipeline/fetch → 200 (subprocess mocké)
  - test_pipeline_fetch_failure   : POST /pipeline/fetch → 500 si subprocess échoue
  - test_pipeline_predict_ok      : POST /pipeline/predict → 200 (subprocess mocké)
  - test_pipeline_predict_failure : POST /pipeline/predict → 500 si subprocess échoue

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


# ─── Tests /monitoring/data ───────────────────────────────────────────────────

def test_monitoring_data_empty():
    """/monitoring/data retourne rows=[] si aucune donnée en base."""
    response = client.get("/monitoring/data?days=7")
    assert response.status_code == 200
    data = response.json()
    assert "rows" in data
    assert "start" in data
    assert "end" in data
    assert isinstance(data["rows"], list)
    assert len(data["rows"]) == 0


def test_monitoring_data_with_rows():
    """/monitoring/data retourne la structure correcte avec données."""
    from datetime import datetime, timedelta
    # Insérer des prédictions récentes
    base = datetime.utcnow() - timedelta(days=1)
    target_times = [(base + timedelta(hours=3 * i)).strftime("%Y-%m-%dT%H:%M") for i in range(8)]
    predicted    = [27.0 + i * 0.5 for i in range(8)]
    insert_predictions(
        model_id         = "test_model",
        generated_at     = target_times[0],
        target_times     = target_times,
        predicted_values = predicted,
        db_path          = _TEST_DB,
    )
    # Insérer des observations réelles correspondantes
    df_weather = pd.DataFrame({
        "timestamp":      target_times,
        "temperature_2m": [26.5 + i * 0.5 for i in range(8)],
    })
    insert_weather_safe(df_weather, db_path=_TEST_DB)

    response = client.get("/monitoring/data?days=7")
    assert response.status_code == 200
    data = response.json()
    assert len(data["rows"]) > 0

    row = data["rows"][0]
    assert "time"      in row
    assert "time_ms"   in row
    assert "predicted" in row
    assert "actual"    in row
    assert "error"     in row
    # time doit être une ISO string
    assert "T" in row["time"]


def test_monitoring_data_days_param():
    """Le paramètre days hors borne (0 ou 91) doit retourner 422."""
    assert client.get("/monitoring/data?days=0").status_code  == 422
    assert client.get("/monitoring/data?days=91").status_code == 422
    assert client.get("/monitoring/data?days=30").status_code == 200


# ─── Tests /monitoring/refresh ────────────────────────────────────────────────

def test_monitoring_refresh_no_data(monkeypatch):
    """/monitoring/refresh retourne status=no_data si aucun point comparé."""
    import api.main as main_module
    import pandas as pd

    # Simuler get_predictions_with_actuals retournant un DataFrame vide
    monkeypatch.setattr(main_module, "get_predictions_with_actuals",
                        lambda start, end: pd.DataFrame())

    response = client.get("/monitoring/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "no_data"


def test_monitoring_refresh_ok():
    """/monitoring/refresh calcule MAE/RMSE/biais si des données existent."""
    from datetime import datetime, timedelta
    base = datetime.utcnow() - timedelta(days=1)
    target_times = [(base + timedelta(hours=3 * i)).strftime("%Y-%m-%dT%H:%M") for i in range(8)]
    insert_predictions(
        model_id         = "test_model",
        generated_at     = target_times[0],
        target_times     = target_times,
        predicted_values = [28.0] * 8,
        db_path          = _TEST_DB,
    )
    df_weather = pd.DataFrame({
        "timestamp":      target_times,
        "temperature_2m": [27.0] * 8,
    })
    insert_weather_safe(df_weather, db_path=_TEST_DB)

    response = client.get("/monitoring/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "mae"      in data
    assert "rmse"     in data
    assert "bias"     in data
    assert "n_points" in data
    assert data["mae"]      >= 0
    assert data["rmse"]     >= 0
    assert data["n_points"] > 0


# ─── Tests /pipeline/fetch et /pipeline/predict ───────────────────────────────

class _FakeProcess:
    """Simule asyncio.subprocess.Process avec returncode configurable."""
    def __init__(self, returncode: int, stdout: bytes = b"ok", stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


def test_pipeline_fetch_ok(monkeypatch):
    """POST /pipeline/fetch retourne 200 si le subprocess réussit."""
    import asyncio
    import api.main as main_module

    async def fake_exec(*args, **kwargs):
        return _FakeProcess(returncode=0, stdout=b"fetch ok")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    response = client.post("/pipeline/fetch")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "date"   in data
    assert "output" in data


def test_pipeline_fetch_failure(monkeypatch):
    """POST /pipeline/fetch retourne 500 si le subprocess échoue."""
    import asyncio

    async def fake_exec(*args, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"fetch error")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    response = client.post("/pipeline/fetch")
    assert response.status_code == 500
    assert "fetch error" in response.json()["detail"]


def test_pipeline_predict_ok(monkeypatch):
    """POST /pipeline/predict retourne 200 si le subprocess réussit."""
    import asyncio

    async def fake_exec(*args, **kwargs):
        return _FakeProcess(returncode=0, stdout=b"predict ok")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    response = client.post("/pipeline/predict")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "date"   in data
    assert "output" in data


def test_pipeline_predict_failure(monkeypatch):
    """POST /pipeline/predict retourne 500 si le subprocess échoue."""
    import asyncio

    async def fake_exec(*args, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"predict error")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    response = client.post("/pipeline/predict")
    assert response.status_code == 500
    assert "predict error" in response.json()["detail"]
