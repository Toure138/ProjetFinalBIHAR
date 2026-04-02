"""
predict.py — Inférence batch LSTM (PyTorch) : génère les prédictions pour une date donnée.

Flux :
  1. Charge les poids LSTM depuis model/lstm_model.pth
  2. Charge les scalers et la config
  3. Récupère l'historique récent depuis SQLite
  4. Construit les features et la séquence d'entrée
  5. Prédit les 24 prochains pas (72h = 3 jours)
  6. Dé-normalise et sauvegarde dans SQLite

Usage :
    python -m src.inference.predict
    python -m src.inference.predict --date 2025-01-15
"""

import argparse
import pickle
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import torch

from src.common.config import (
    DB_PATH, FORECAST_HORIZON, LSTM_CONFIG_PATH, LSTM_MODEL_PATH,
    MODEL_DIR, SCALER_PATH, SCALER_TARGET_PATH, SEQUENCE_LENGTH,
)
from src.common.database import get_weather, insert_predictions, init_db
from src.common.logger import get_logger
from src.training.train import LSTMModel, build_features

logger = get_logger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_lstm():
    """
    Charge le modèle LSTM, les scalers et la config.
    Returns: (model, scaler, scaler_target, model_config)
    """
    if not LSTM_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modèle non trouvé : {LSTM_MODEL_PATH}\n"
            "Lancer d'abord : python -m src.training.train"
        )

    with open(LSTM_CONFIG_PATH, "rb") as f:
        cfg = pickle.load(f)
    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)
    with open(SCALER_TARGET_PATH, "rb") as f:
        scaler_target = pickle.load(f)

    model = LSTMModel(
        n_features  = cfg["n_features"],
        horizon     = cfg["horizon"],
        units       = cfg.get("lstm_units",  [128, 64, 32]),
        dense_units = cfg.get("dense_units", [64, 32]),
        dropout     = cfg.get("dropout",     0.2),
    )
    model.load_state_dict(torch.load(str(LSTM_MODEL_PATH), map_location=DEVICE))
    model.to(DEVICE)
    model.eval()
    logger.info("Modèle LSTM chargé depuis %s", LSTM_MODEL_PATH)

    return model, scaler, scaler_target, cfg


def get_model_id() -> str:
    run_id_path = MODEL_DIR / "latest_run_id.txt"
    return run_id_path.read_text().strip() if run_id_path.exists() else "lstm_local"


def predict_from_date(date_str: str) -> pd.DataFrame:
    """
    Génère les prédictions LSTM pour les 3 jours suivant date_str.
    """
    init_db()
    model, scaler, scaler_target, cfg = load_lstm()
    feature_cols = cfg["feature_columns"]

    # ── Historique ────────────────────────────────────────────────────────────
    ref_dt     = pd.Timestamp(date_str)
    hist_start = (ref_dt - timedelta(days=20)).strftime("%Y-%m-%d")
    logger.info("Chargement historique : %s → %s", hist_start, date_str)
    df_raw = get_weather(hist_start, date_str)

    if len(df_raw) < SEQUENCE_LENGTH + 50:
        raise ValueError(
            f"Pas assez d'historique ({len(df_raw)} pas). "
            "Vérifier la présence des données dans la base."
        )

    # ── Features + normalisation ──────────────────────────────────────────────
    df_feat = build_features(df_raw)
    missing = [c for c in feature_cols if c not in df_feat.columns]
    if missing:
        raise ValueError(f"Features manquantes : {missing}")

    df_feat[feature_cols] = scaler.transform(df_feat[feature_cols])

    # ── Dernière séquence ─────────────────────────────────────────────────────
    X_last  = df_feat[feature_cols].values[-SEQUENCE_LENGTH:]          # (24, n_feat)
    X_input = torch.from_numpy(X_last[np.newaxis].astype(np.float32)).to(DEVICE)  # (1,24,n)

    # ── Prédiction ────────────────────────────────────────────────────────────
    with torch.no_grad():
        y_pred_sc = model(X_input).cpu().numpy().flatten()  # (24,)

    y_pred = scaler_target.inverse_transform(
        y_pred_sc.reshape(-1, 1)
    ).flatten()  # (24,) en °C

    # ── Timestamps cibles ─────────────────────────────────────────────────────
    last_ts      = pd.Timestamp(df_feat["timestamp"].iloc[-1])
    target_times = [
        (last_ts + timedelta(hours=3 * (i + 1))).strftime("%Y-%m-%dT%H:%M")
        for i in range(FORECAST_HORIZON)
    ]

    result = pd.DataFrame({"target_time": target_times, "predicted": y_pred})
    logger.info("Prédictions LSTM générées : %d pas (%.1f → %.1f °C)",
                len(result), y_pred.min(), y_pred.max())
    return result


def run_batch_inference(date_str: str) -> int:
    predictions  = predict_from_date(date_str)
    model_id     = get_model_id()
    generated_at = f"{date_str}T00:00"
    inserted = insert_predictions(
        model_id         = model_id,
        generated_at     = generated_at,
        target_times     = predictions["target_time"].tolist(),
        predicted_values = predictions["predicted"].tolist(),
    )
    return inserted


# ─── Point d'entrée CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Génère les prédictions LSTM batch pour une date donnée"
    )
    parser.add_argument(
        "--date",
        default=datetime.today().strftime("%Y-%m-%d"),
        help="Date de génération YYYY-MM-DD (défaut: aujourd'hui)",
    )
    args = parser.parse_args()
    n = run_batch_inference(args.date)
    print(f"✓ {n} prédictions LSTM sauvegardées pour le {args.date}")
