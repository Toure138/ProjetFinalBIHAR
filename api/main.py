"""
main.py — API REST FastAPI pour les prédictions de température.

Endpoints :
  GET /predictions          → prédictions pour une date donnée
  GET /predictions/combined → prédictions + valeurs réelles sur une période
  GET /version              → version logicielle et version modèle

Lancement local :
    uvicorn api.main:app --reload --port 8000

Documentation auto :
    http://localhost:8000/docs
"""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

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


# ─── Middleware : log de chaque requête ───────────────────────────────────────

@app.middleware("http")
async def log_requests(request, call_next):
    """
    Logue automatiquement chaque requête HTTP :
    méthode, path, durée et code de statut.
    """
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)

    logger.info(
        "%s %s → %d  (%.1f ms)",
        request.method, request.url.path,
        response.status_code, duration_ms,
    )
    return response


# ─── Endpoint 1 : prédictions pour une date ───────────────────────────────────

@app.get("/predictions", summary="Prédictions pour une date de génération")
def get_preds(
    date: str = Query(
        ...,
        description="Date de génération des prédictions (YYYY-MM-DD)",
        examples="2025-01-15",
    )
):
    """
    Retourne les 24 prédictions (72h = 3 jours) générées à la date donnée.

    - **date** : date à laquelle les prédictions ont été calculées
    """
    logger.info("GET /predictions?date=%s", date)

    df = get_predictions(date)

    if df.empty:
        logger.warning("Aucune prédiction trouvée pour date=%s", date)
        raise HTTPException(
            status_code=404,
            detail=f"Aucune prédiction disponible pour la date '{date}'. "
                   "Lancer d'abord : python -m src.inference.predict --date " + date,
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
    start: str = Query(
        ...,
        description="Date de début (YYYY-MM-DD)",
        examples="2025-01-10",
    ),
    end: str = Query(
        ...,
        description="Date de fin (YYYY-MM-DD)",
        examples="2025-01-13",
    ),
):
    """
    Retourne les prédictions combinées avec les observations réelles
    pour calculer les erreurs (monitoring).

    Les lignes sans observation réelle ont `actual=null` et `error=null`.
    """
    logger.info("GET /predictions/combined?start=%s&end=%s", start, end)

    df = get_predictions_with_actuals(start, end)

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune donnée disponible pour la période {start} → {end}.",
        )

    # Statistiques d'erreur (sur les lignes où on a les deux)
    df_clean = df.dropna(subset=["actual"])
    summary = {}
    if not df_clean.empty:
        summary = {
            "n_points_with_actual": len(df_clean),
            "mae":  round(df_clean["error"].abs().mean(), 4),
            "bias": round(df_clean["error"].mean(), 4),
        }

    return {
        "start":   start,
        "end":     end,
        "summary": summary,
        "data":    df.fillna("null").to_dict("records"),
    }


# ─── Endpoint 3 : version ─────────────────────────────────────────────────────

@app.get("/version", summary="Version logicielle et version modèle")
def get_version():
    """
    Retourne :
    - **software_version** : '0.0.0' en local, commit ID en CI/CD
    - **model_version**    : run_id MLflow du dernier modèle entraîné
    """
    logger.info("GET /version")

    # Lire le run_id MLflow sauvegardé par le pipeline d'entraînement
    run_id_path = MODEL_DIR / "latest_run_id.txt"
    model_version = run_id_path.read_text().strip() if run_id_path.exists() else "unknown"

    return {
        "software_version": SOFTWARE_VERSION,
        "model_version":    model_version,
    }


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", summary="Vérification de l'état de l'API", include_in_schema=False)
def health():
    return {"status": "ok"}
