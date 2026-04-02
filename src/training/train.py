"""
train.py — Pipeline d'entraînement du modèle LSTM (PyTorch).

Flux :
  1. Chargement des données depuis SQLite
  2. Feature engineering (sin/cos cycliques, lags, rolling)
  3. Split train / val / test chronologique
  4. Construction des séquences (X, y) pour le LSTM
  5. Normalisation (StandardScaler)
  6. Entraînement LSTM avec PyTorch (EarlyStopping manuel)
  7. Évaluation (MAE, RMSE par horizon)
  8. Sauvegarde du modèle, des scalers et de la config
  9. Logging des métriques et artefacts dans MLflow

Usage :
    python -m src.training.train
    python -m src.training.train --start 2023-01-01 --end 2025-01-31
"""

import argparse
import pickle
import time
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

from src.common.config import (
    BATCH_SIZE, CYCLICAL_FEATURES, DB_PATH, FORECAST_HORIZON,
    LSTM_CONFIG_PATH, LSTM_DENSE_UNITS, LSTM_DROPOUT, LSTM_LEARNING_RATE,
    LSTM_MODEL_PATH, LSTM_UNITS, MAX_EPOCHS, MLFLOW_EXPERIMENT,
    MLFLOW_TRACKING_URI, MODEL_DIR, MODEL_NAME, PATIENCE,
    SCALER_PATH, SCALER_TARGET_PATH, SEQUENCE_LENGTH,
    TRAIN_RATIO, VAL_RATIO,
)
from src.common.database import get_weather, init_db
from src.common.logger import get_logger

logger = get_logger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─── Feature Engineering ─────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Crée les features à partir de la série temporelle.
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    t = df["timestamp"]

    # Features cycliques
    df["hour_sin"]  = np.sin(2 * np.pi * t.dt.hour / 24)
    df["hour_cos"]  = np.cos(2 * np.pi * t.dt.hour / 24)
    df["day_sin"]   = np.sin(2 * np.pi * t.dt.dayofyear / 365.25)
    df["day_cos"]   = np.cos(2 * np.pi * t.dt.dayofyear / 365.25)
    df["month_sin"] = np.sin(2 * np.pi * t.dt.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * t.dt.month / 12)

    # Features temporelles brutes
    df["hour"]       = t.dt.hour
    df["dayofweek"]  = t.dt.dayofweek
    df["month"]      = t.dt.month
    df["is_weekend"] = (t.dt.dayofweek >= 5).astype(int)

    # Lag features
    for lag in list(range(1, 25)) + [36, 48]:
        df[f"lag_{lag}"] = df["temperature_2m"].shift(lag)

    # Rolling statistics
    for window in [3, 6, 8, 12, 24]:
        df[f"rolling_mean_{window}"] = df["temperature_2m"].rolling(window).mean()
        df[f"rolling_std_{window}"]  = df["temperature_2m"].rolling(window).std()

    # Différences
    for d in [1, 2, 8]:
        df[f"diff_{d}"] = df["temperature_2m"].diff(d)

    df = df.dropna().reset_index(drop=True)
    return df


# ─── Construction des séquences ──────────────────────────────────────────────

def make_sequences(df: pd.DataFrame, feature_cols: list) -> tuple:
    X_list, y_list = [], []
    values_feat   = df[feature_cols].values
    values_target = df["temperature_2m"].values
    for i in range(len(df) - SEQUENCE_LENGTH - FORECAST_HORIZON + 1):
        X_list.append(values_feat[i: i + SEQUENCE_LENGTH])
        y_list.append(values_target[i + SEQUENCE_LENGTH: i + SEQUENCE_LENGTH + FORECAST_HORIZON])
    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)


# ─── Évaluation multi-horizon ────────────────────────────────────────────────

def evaluate_multistep(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    KEY_HORIZONS = {
        "+3h  (pas 1)": 0,
        "+24h (J+1)":   7,
        "+48h (J+2)":  15,
        "+72h (J+3)":  23,
    }
    results = {}
    for label, idx in KEY_HORIZONS.items():
        yt, yp = y_true[:, idx], y_pred[:, idx]
        results[label] = {
            "mae":  mean_absolute_error(yt, yp),
            "rmse": np.sqrt(mean_squared_error(yt, yp)),
        }
    n = min(len(y_true), len(y_pred))
    results["global"] = {
        "mae":  mean_absolute_error(y_true[:n].flatten(), y_pred[:n].flatten()),
        "rmse": np.sqrt(mean_squared_error(y_true[:n].flatten(), y_pred[:n].flatten())),
    }
    return results


# ─── Modèle LSTM PyTorch ──────────────────────────────────────────────────────

class LSTMModel(nn.Module):
    """
    LSTM multi-step :
        LSTM(128) → LSTM(64) → LSTM(32) → Dense(64) → Dense(32) → Dense(horizon)
    """
    def __init__(self, n_features: int, horizon: int,
                 units=None, dense_units=None, dropout: float = 0.2):
        super().__init__()
        units       = units       or [128, 64, 32]
        dense_units = dense_units or [64, 32]

        self.lstms = nn.ModuleList()
        self.drops = nn.ModuleList()
        in_size = n_features
        for i, u in enumerate(units):
            self.lstms.append(nn.LSTM(in_size, u, batch_first=True))
            self.drops.append(nn.Dropout(dropout))
            in_size = u

        layers = []
        for du in dense_units:
            layers += [nn.Linear(in_size, du), nn.ReLU(), nn.Dropout(dropout)]
            in_size = du
        layers.append(nn.Linear(in_size, horizon))
        self.fc = nn.Sequential(*layers)

    def forward(self, x):
        # x : (batch, seq_len, n_features)
        for lstm, drop in zip(self.lstms, self.drops):
            x, _ = lstm(x)
            x = drop(x)
        x = x[:, -1, :]   # dernier pas de temps
        return self.fc(x)


# ─── Pipeline principal ───────────────────────────────────────────────────────

def run_training(start: str = "2023-01-01", end: str = "2025-01-31") -> str:
    init_db()

    # ── 1. Données ─────────────────────────────────────────────────────────────
    logger.info("Chargement des données depuis SQLite (%s → %s)", start, end)
    df_raw = get_weather(start, end)
    if df_raw.empty:
        raise ValueError("Aucune donnée en base. Lancer d'abord : python -m src.data.fetch_data")

    # ── 2. Features ────────────────────────────────────────────────────────────
    df = build_features(df_raw)
    feature_cols = [c for c in df.columns if c not in ["timestamp", "temperature_2m"]]
    logger.info("Features : %d colonnes", len(feature_cols))

    # ── 3. Split chronologique ─────────────────────────────────────────────────
    n       = len(df)
    n_train = int(n * TRAIN_RATIO)
    n_val   = int(n * VAL_RATIO)
    df_train = df.iloc[:n_train]
    df_val   = df.iloc[n_train: n_train + n_val]
    df_test  = df.iloc[n_train + n_val:]
    logger.info("Split → train: %d | val: %d | test: %d", len(df_train), len(df_val), len(df_test))

    # ── 4. Normalisation ───────────────────────────────────────────────────────
    scaler        = StandardScaler()
    scaler_target = StandardScaler()
    scaler.fit(df_train[feature_cols])
    scaler_target.fit(df_train[["temperature_2m"]])

    def scale_df(d):
        d = d.copy()
        d[feature_cols]     = scaler.transform(d[feature_cols])
        d["temperature_2m"] = scaler_target.transform(d[["temperature_2m"]])
        return d

    buf = SEQUENCE_LENGTH + FORECAST_HORIZON
    df_train_sc = scale_df(df_train)
    df_val_sc   = scale_df(pd.concat([df_train.iloc[-buf:], df_val]))
    df_test_sc  = scale_df(pd.concat([df_val.iloc[-buf:],   df_test]))

    # ── 5. Séquences → Tensors ─────────────────────────────────────────────────
    X_train, y_train = make_sequences(df_train_sc, feature_cols)
    X_val,   y_val   = make_sequences(df_val_sc,   feature_cols)
    X_test,  y_test  = make_sequences(df_test_sc,  feature_cols)
    logger.info("Séquences → train: %d | val: %d | test: %d", len(X_train), len(X_val), len(X_test))

    def to_loader(X, y, shuffle=False):
        ds = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
        return DataLoader(ds, batch_size=BATCH_SIZE, shuffle=shuffle)

    train_loader = to_loader(X_train, y_train, shuffle=True)
    val_loader   = to_loader(X_val,   y_val)
    test_loader  = to_loader(X_test,  y_test)

    # ── 6. Entraînement ────────────────────────────────────────────────────────
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    with mlflow.start_run() as run:
        run_id = run.info.run_id
        logger.info("MLflow run_id : %s", run_id)

        # ── Datasets used (visible dans l'onglet MLflow) ──────────────────────
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ds_train = mlflow.data.from_pandas(
                df_train[["timestamp", "temperature_2m"]],
                name   = "weather_train",
                source = str(DB_PATH),
            )
            ds_val = mlflow.data.from_pandas(
                df_val[["timestamp", "temperature_2m"]],
                name   = "weather_val",
                source = str(DB_PATH),
            )
            ds_test = mlflow.data.from_pandas(
                df_test[["timestamp", "temperature_2m"]],
                name   = "weather_test",
                source = str(DB_PATH),
            )
        mlflow.log_input(ds_train, context="training")
        mlflow.log_input(ds_val,   context="validation")
        mlflow.log_input(ds_test,  context="test")

        mlflow.log_params({
            "model":           "LSTM",
            "framework":       "PyTorch",
            "sequence_length": SEQUENCE_LENGTH,
            "horizon":         FORECAST_HORIZON,
            "lstm_units":      str(LSTM_UNITS),
            "dense_units":     str(LSTM_DENSE_UNITS),
            "dropout":         LSTM_DROPOUT,
            "learning_rate":   LSTM_LEARNING_RATE,
            "batch_size":      BATCH_SIZE,
            "n_features":      X_train.shape[2],
        })

        model = LSTMModel(
            n_features  = X_train.shape[2],
            horizon     = FORECAST_HORIZON,
            units       = LSTM_UNITS,
            dense_units = LSTM_DENSE_UNITS,
            dropout     = LSTM_DROPOUT,
        ).to(DEVICE)

        optimizer = torch.optim.Adam(model.parameters(), lr=LSTM_LEARNING_RATE)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, factor=0.5, patience=5, min_lr=1e-6
        )
        criterion = nn.MSELoss()

        best_val_loss = float("inf")
        patience_cnt  = 0
        best_state    = None

        t0 = time.time()
        for epoch in range(1, MAX_EPOCHS + 1):
            # Train
            model.train()
            train_losses = []
            for xb, yb in train_loader:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                optimizer.zero_grad()
                loss = criterion(model(xb), yb)
                loss.backward()
                optimizer.step()
                train_losses.append(loss.item())

            # Val
            model.eval()
            val_losses = []
            with torch.no_grad():
                for xb, yb in val_loader:
                    xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                    val_losses.append(criterion(model(xb), yb).item())

            t_loss = np.mean(train_losses)
            v_loss = np.mean(val_losses)
            scheduler.step(v_loss)

            if epoch % 10 == 0 or epoch == 1:
                logger.info("Epoch %3d/%d  train=%.5f  val=%.5f", epoch, MAX_EPOCHS, t_loss, v_loss)

            if v_loss < best_val_loss:
                best_val_loss = v_loss
                best_state    = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                patience_cnt  = 0
            else:
                patience_cnt += 1
                if patience_cnt >= PATIENCE:
                    logger.info("EarlyStopping à l'epoch %d (patience=%d)", epoch, PATIENCE)
                    break

        train_time = time.time() - t0
        logger.info("LSTM entraîné en %.1fs | best_val_loss=%.5f", train_time, best_val_loss)
        mlflow.log_metric("train_time_s",  round(train_time,    1))
        mlflow.log_metric("best_val_loss", round(best_val_loss, 6))

        # Restaurer les meilleurs poids
        if best_state:
            model.load_state_dict(best_state)

        # ── 7. Évaluation ──────────────────────────────────────────────────────
        model.eval()
        preds, trues = [], []
        with torch.no_grad():
            for xb, yb in test_loader:
                preds.append(model(xb.to(DEVICE)).cpu().numpy())
                trues.append(yb.numpy())
        y_pred_sc = np.vstack(preds)
        y_true_sc = np.vstack(trues)

        def inv(arr):
            flat = arr.flatten().reshape(-1, 1)
            return scaler_target.inverse_transform(flat).flatten().reshape(arr.shape)

        y_pred = inv(y_pred_sc)
        y_true = inv(y_true_sc)

        metrics = evaluate_multistep(y_true, y_pred)
        for label, m in metrics.items():
            logger.info("  %-20s  MAE=%.4f  RMSE=%.4f", label, m["mae"], m["rmse"])
            # Nettoyer le nom : MLflow interdit +, (, ), espaces multiples
            safe = label.replace("+", "p").replace("(", "").replace(")", "").strip().replace("  ", "_").replace(" ", "_")
            mlflow.log_metric(f"mae_{safe}",  round(m["mae"],  4))
            mlflow.log_metric(f"rmse_{safe}", round(m["rmse"], 4))

        # ── 8. Sauvegarde ──────────────────────────────────────────────────────
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        torch.save(model.state_dict(), str(LSTM_MODEL_PATH))
        logger.info("Modèle LSTM sauvegardé : %s", LSTM_MODEL_PATH)

        with open(SCALER_PATH, "wb") as f:
            pickle.dump(scaler, f)
        with open(SCALER_TARGET_PATH, "wb") as f:
            pickle.dump(scaler_target, f)

        model_config = {
            "sequence_length": SEQUENCE_LENGTH,
            "n_features":      X_train.shape[2],
            "horizon":         FORECAST_HORIZON,
            "feature_columns": feature_cols,
            "target_column":   "temperature_2m",
            "lstm_units":      LSTM_UNITS,
            "dense_units":     LSTM_DENSE_UNITS,
            "dropout":         LSTM_DROPOUT,
        }
        with open(LSTM_CONFIG_PATH, "wb") as f:
            pickle.dump(model_config, f)

        # ── Enregistrement MLflow du modèle (crée "Logged models") ───────────
        # Exemple d'input pour la signature MLflow
        sample_input  = torch.zeros(1, SEQUENCE_LENGTH, X_train.shape[2])
        sample_output = model(sample_input.to(DEVICE)).detach().cpu()

        signature = mlflow.models.infer_signature(
            sample_input.numpy(),
            sample_output.numpy(),
        )

        mlflow.pytorch.log_model(
            pytorch_model         = model,
            artifact_path         = "lstm_model",
            signature             = signature,
            registered_model_name = MODEL_NAME,   # crée aussi "Registered models"
        )
        logger.info("Modèle enregistré dans MLflow : %s", MODEL_NAME)

        # Artefacts complémentaires (scalers, config)
        mlflow.log_artifact(str(SCALER_PATH))
        mlflow.log_artifact(str(LSTM_CONFIG_PATH))

        (MODEL_DIR / "latest_run_id.txt").write_text(run_id)

    return run_id


# ─── Point d'entrée CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entraîne le modèle LSTM (PyTorch)")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end",   default="2025-01-31")
    args = parser.parse_args()
    run_id = run_training(args.start, args.end)
    print(f"✓ Entraînement LSTM terminé. MLflow run_id : {run_id}")
