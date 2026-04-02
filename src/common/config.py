"""
config.py — Paramètres centralisés du projet.

Toutes les constantes (chemins, hyperparamètres, noms) sont ici.
Un seul endroit à modifier si un chemin change.
"""

import os
from pathlib import Path

# ─── Racine du projet ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]   # Projet_final/

# ─── Chemins des dossiers ──────────────────────────────────────────────────────
DATA_DIR        = ROOT / "data"
MODEL_DIR       = ROOT / "model" / "registry"   # registre des modèles entraînés
MONITORING_DIR  = ROOT / "monitoring" / "output"
MLFLOW_DIR      = ROOT / "mlruns"

# ─── Base de données SQLite ────────────────────────────────────────────────────
DB_PATH = DATA_DIR / "weather.db"

# ─── Source des données météo (API Open-Meteo) ────────────────────────────────
LATITUDE   = 6.816667    # Côte d'Ivoire
LONGITUDE  = -5.283333
TIMEZONE   = "UTC"
VARIABLE   = "temperature_2m"

# ─── Série temporelle ─────────────────────────────────────────────────────────
FREQ_HOURS       = 3    # pas de 3h
FORECAST_HORIZON = 24   # 24 pas × 3h = 72h = 3 jours
SEQUENCE_LENGTH  = 24   # historique fourni au modèle (même durée = 3 jours)

# ─── Split train / val / test ──────────────────────────────────────────────────
TRAIN_RATIO = 0.70
VAL_RATIO   = 0.15
# Test = 1 - 0.70 - 0.15 = 0.15

# ─── Hyperparamètres LSTM ─────────────────────────────────────────────────────
LSTM_UNITS        = [128, 64, 32]   # unités par couche LSTM
LSTM_DENSE_UNITS  = [64, 32]        # unités des couches Dense intermédiaires
LSTM_DROPOUT      = 0.2
LSTM_LEARNING_RATE = 1e-3
BATCH_SIZE        = 32
MAX_EPOCHS        = 100
PATIENCE          = 10              # EarlyStopping

# ─── Features cycliques (calendrier) ──────────────────────────────────────────
CYCLICAL_FEATURES = [
    "hour_sin", "hour_cos",
    "day_sin",  "day_cos",
    "month_sin","month_cos",
]

# ─── Fichiers du modèle sauvegardé ────────────────────────────────────────────
LSTM_MODEL_PATH    = MODEL_DIR / "lstm_model.pth"       # poids PyTorch (state_dict)
SCALER_PATH        = MODEL_DIR / "scaler.pkl"           # StandardScaler des features
SCALER_TARGET_PATH = MODEL_DIR / "scaler_target.pkl"    # StandardScaler de la cible
LSTM_CONFIG_PATH   = MODEL_DIR / "lstm_config.pkl"      # métadonnées du modèle

# ─── MLflow ───────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = MLFLOW_DIR.as_uri()   # file:///C:/... — requis sur Windows
MLFLOW_EXPERIMENT   = "temperature_forecast"
MODEL_NAME          = "lstm_temperature"

# ─── Version logicielle ───────────────────────────────────────────────────────
# En local → "0.0.0" ; en CI/CD → remplacé par le commit ID via variable d'env.
SOFTWARE_VERSION = os.getenv("GIT_COMMIT_ID", "0.0.0")
