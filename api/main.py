"""
main.py — API REST FastAPI pour les prédictions de température.

Endpoints :
  GET /predictions            → prédictions pour une date donnée
  GET /predictions/combined   → prédictions + valeurs réelles sur une période
  GET /version                → version logicielle et version modèle
  GET /monitoring/data        → données brutes pour Grafana (prédictions + réel)
  GET /monitoring/refresh     → recalcul immédiat des métriques Prometheus
  GET /metrics                → métriques Prometheus (HTTP + qualité modèle)

Lancement local :
    uvicorn api.main:app --reload --port 8000

Documentation auto :
    http://localhost:8000/docs
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Imports internes (chemin relatif depuis la racine du projet)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import MODEL_DIR, SOFTWARE_VERSION
from src.common.database import get_predictions, get_predictions_with_actuals, init_db
from src.common.logger import get_logger

# ─── Application ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Temperature Forecast API",
    description="API de prévision de température à horizon 3 jours (pas 3h)",
    version="0.0.1",
)

logger = get_logger(__name__)

# Initialiser la BDD au démarrage
init_db()

# ─── Prometheus HTTP metrics (/metrics) ───────────────────────────────────────
Instrumentator().instrument(app).expose(app)

# ─── Métriques custom Prometheus : qualité du modèle ─────────────────────────
# Visibles dans Grafana via le scrape Prometheus existant.
# Rafraîchies automatiquement toutes les heures + via /monitoring/refresh.

GAUGE_MAE = Gauge(
    "model_monitoring_mae",
    "MAE (Mean Absolute Error) predictions vs observations sur les 7 derniers jours",
)
GAUGE_RMSE = Gauge(
    "model_monitoring_rmse",
    "RMSE predictions vs observations sur les 7 derniers jours",
)
GAUGE_BIAS = Gauge(
    "model_monitoring_bias",
    "Biais moyen (predicted - actual) sur les 7 derniers jours",
)
GAUGE_N = Gauge(
    "model_monitoring_n_points",
    "Nombre de points comparés sur les 7 derniers jours",
)

MONITORING_INTERVAL_SECONDS = 3600  # toutes les heures


def _compute_and_update_gauges() -> dict:
    """Calcule MAE/RMSE/biais sur les 7 derniers jours et met à jour les jauges."""
    end   = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

    df = get_predictions_with_actuals(start, end)
    df_clean = df.dropna(subset=["predicted", "actual"]) if not df.empty else df

    if df_clean.empty:
        logger.warning("Monitoring : aucune donnée pour %s → %s", start, end)
        return {"status": "no_data", "start": start, "end": end}

    mae  = float(mean_absolute_error(df_clean["actual"], df_clean["predicted"]))
    rmse = float(np.sqrt(mean_squared_error(df_clean["actual"], df_clean["predicted"])))
    bias = float((df_clean["predicted"] - df_clean["actual"]).mean())
    n    = len(df_clean)

    GAUGE_MAE.set(mae)
    GAUGE_RMSE.set(rmse)
    GAUGE_BIAS.set(bias)
    GAUGE_N.set(n)

    logger.info("Monitoring → MAE=%.4f RMSE=%.4f Biais=%.4f N=%d", mae, rmse, bias, n)
    return {
        "status": "ok",
        "start": start, "end": end,
        "mae": round(mae, 4), "rmse": round(rmse, 4),
        "bias": round(bias, 4), "n_points": n,
    }


async def _monitoring_background_task():
    """Tâche asyncio : recalcule les métriques toutes les heures."""
    await asyncio.sleep(5)
    while True:
        try:
            _compute_and_update_gauges()
        except Exception as exc:
            logger.error("Monitoring background task error: %s", exc)
        await asyncio.sleep(MONITORING_INTERVAL_SECONDS)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_monitoring_background_task())


# ─── Middleware : log de chaque requête ───────────────────────────────────────

@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info("%s %s → %d  (%.1f ms)",
                request.method, request.url.path,
                response.status_code, duration_ms)
    return response


# ─── Endpoint 1 : prédictions pour une date ───────────────────────────────────

@app.get("/predictions", summary="Prédictions pour une date de génération")
def get_preds(
    date: str = Query(..., description="Date de génération (YYYY-MM-DD)", examples="2025-01-15")
):
    logger.info("GET /predictions?date=%s", date)
    df = get_predictions(date)
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune prédiction pour '{date}'. "
                   "Lancer : python -m src.inference.predict --date " + date,
        )
    return {
        "date":        date,
        "model_id":    df["model_id"].iloc[0],
        "n_steps":     len(df),
        "predictions": df[["horizon_step", "target_time", "predicted"]].to_dict("records"),
    }


# ─── Endpoint 2 : prédictions + réel sur une période ─────────────────────────

@app.get("/predictions/combined", summary="Prédictions + valeurs réelles")
def get_combined(
    start: str = Query(..., description="Date de début (YYYY-MM-DD)", examples="2025-01-10"),
    end:   str = Query(..., description="Date de fin   (YYYY-MM-DD)", examples="2025-01-13"),
):
    logger.info("GET /predictions/combined?start=%s&end=%s", start, end)
    df = get_predictions_with_actuals(start, end)
    if df.empty:
        raise HTTPException(status_code=404,
                            detail=f"Aucune donnée pour {start} → {end}.")
    df_clean = df.dropna(subset=["actual"])
    summary = {}
    if not df_clean.empty:
        summary = {
            "n_points_with_actual": len(df_clean),
            "mae":  round(df_clean["error"].abs().mean(), 4),
            "bias": round(df_clean["error"].mean(), 4),
        }
    return {"start": start, "end": end, "summary": summary,
            "data": df.fillna("null").to_dict("records")}


# ─── Endpoint 3 : version ─────────────────────────────────────────────────────

@app.get("/version", summary="Version logicielle et version modèle")
def get_version():
    logger.info("GET /version")
    run_id_path = MODEL_DIR / "latest_run_id.txt"
    model_version = run_id_path.read_text().strip() if run_id_path.exists() else "unknown"
    return {"software_version": SOFTWARE_VERSION, "model_version": model_version}


# ─── Endpoint 4 : données brutes pour Grafana ────────────────────────────────
# Utilisé par le plugin Grafana Infinity pour afficher :
#   - la courbe "prédictions vs réel" (remplacement du graphique matplotlib)
#   - le tableau d'erreurs
# Format retourné : liste de {time_ms, predicted, actual, error}
# time_ms = timestamp Unix en millisecondes (format attendu par Grafana)

@app.get("/monitoring/data", summary="Données prédictions vs réel pour Grafana")
def monitoring_data(
    days: int = Query(
        default=7,
        description="Nombre de jours à récupérer (défaut : 7)",
        ge=1, le=90,
    )
):
    """
    Retourne les prédictions et les observations réelles sous forme de tableau JSON
    directement consommable par le plugin Grafana Infinity.

    Chaque ligne : { time_ms, predicted, actual, error }
    - time_ms : timestamp Unix en millisecondes
    - predicted / actual : températures en °C
    - error : predicted − actual (null si actual manquant)
    """
    end   = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    df = get_predictions_with_actuals(start, end)
    if df.empty:
        return {"start": start, "end": end, "rows": []}

    df = df.copy()
    df["target_time"] = pd.to_datetime(df["target_time"])
    df = df.sort_values("target_time")

    # Convertir le timestamp en millisecondes pour Grafana
    df["time_ms"] = (df["target_time"].astype("int64") // 1_000_000).astype(int)

    rows = df[["time_ms", "predicted", "actual", "error"]].where(
        df[["time_ms", "predicted", "actual", "error"]].notna(), other=None
    ).to_dict("records")

    return {"start": start, "end": end, "rows": rows}


# ─── Endpoint 5 : rafraîchissement manuel des métriques Prometheus ───────────

@app.get("/monitoring/refresh", summary="Recalcul immédiat des métriques Prometheus")
def monitoring_refresh():
    """Force le recalcul de MAE/RMSE/biais et met à jour les jauges Prometheus."""
    logger.info("GET /monitoring/refresh")
    return _compute_and_update_gauges()


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}
