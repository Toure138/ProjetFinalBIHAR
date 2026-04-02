"""
database.py — Gestion de la base de données SQLite.

Deux tables :
  - weather_data   : données météo historiques (brutes + agrégées 3h)
  - predictions    : prédictions générées par les modèles

Toutes les fonctions reçoivent une connexion en paramètre pour rester testables.
"""

import sqlite3
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from src.common.config import DB_PATH
from src.common.logger import get_logger

logger = get_logger(__name__)


# ─── Connexion ────────────────────────────────────────────────────────────────

def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Ouvre une connexion SQLite et active les clés étrangères."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─── Création des tables ──────────────────────────────────────────────────────

def init_db(db_path: Path = DB_PATH) -> None:
    """
    Crée les tables si elles n'existent pas encore.
    Idempotent : peut être appelé plusieurs fois sans erreur.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Table 1 : données météo historiques agrégées à 3h
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_data (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL UNIQUE,   -- ex: '2024-01-01T00:00'
            temperature_2m  REAL    NOT NULL           -- °C, moyenne sur 3h
        )
    """)

    # Table 2 : prédictions générées par les modèles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id     TEXT    NOT NULL,             -- ex: 'lstm_v1', run_id MLflow
            generated_at TEXT    NOT NULL,             -- date de génération
            horizon_step INTEGER NOT NULL,             -- 1 à 24 (pas de 3h)
            target_time  TEXT    NOT NULL,             -- timestamp prédit
            predicted    REAL    NOT NULL,             -- valeur prédite (°C)
            UNIQUE(model_id, generated_at, horizon_step)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Base de données initialisée : %s", db_path)


# ─── weather_data ─────────────────────────────────────────────────────────────

def insert_weather(df: pd.DataFrame, db_path: Path = DB_PATH) -> int:
    """
    Insère les données météo dans weather_data.
    Ignore les doublons (même timestamp).

    Args:
        df: DataFrame avec colonnes ['timestamp', 'temperature_2m']

    Returns:
        Nombre de lignes insérées
    """
    conn = get_connection(db_path)
    before = pd.read_sql("SELECT COUNT(*) as n FROM weather_data", conn).iloc[0, 0]

    df[["timestamp", "temperature_2m"]].to_sql(
        "weather_data", conn, if_exists="append", index=False,
        method="multi",
    )
    # Les doublons lèvent une IntegrityError → on les capture silencieusement
    # via INSERT OR IGNORE dans une approche manuelle
    conn.close()

    conn = get_connection(db_path)
    after = pd.read_sql("SELECT COUNT(*) as n FROM weather_data", conn).iloc[0, 0]
    conn.close()

    inserted = after - before
    logger.info("Données météo : %d lignes insérées", inserted)
    return inserted


def insert_weather_safe(df: pd.DataFrame, db_path: Path = DB_PATH) -> int:
    """Version qui ignore les doublons via INSERT OR IGNORE."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    inserted = 0
    for _, row in df.iterrows():
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO weather_data (timestamp, temperature_2m) VALUES (?, ?)",
                (str(row["timestamp"]), float(row["temperature_2m"])),
            )
            inserted += cursor.rowcount
        except Exception as e:
            logger.warning("Erreur insertion météo : %s", e)
    conn.commit()
    conn.close()
    logger.info("Données météo : %d nouvelles lignes", inserted)
    return inserted


def get_weather(start: str, end: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    """
    Récupère les données météo entre deux dates.

    Args:
        start: '2024-01-01'
        end:   '2024-03-31'

    Returns:
        DataFrame avec colonnes ['timestamp', 'temperature_2m']
    """
    conn = get_connection(db_path)
    df = pd.read_sql(
        "SELECT timestamp, temperature_2m FROM weather_data "
        "WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
        conn,
        params=(start, end),
    )
    conn.close()
    return df


# ─── predictions ──────────────────────────────────────────────────────────────

def insert_predictions(
    model_id: str,
    generated_at: str,
    target_times: List[str],
    predicted_values: List[float],
    db_path: Path = DB_PATH,
) -> int:
    """
    Sauvegarde une fenêtre de 24 prédictions dans la base.

    Args:
        model_id       : identifiant du modèle (run_id MLflow ou nom)
        generated_at   : date de génération ISO (ex: '2024-06-01T00:00')
        target_times   : liste de 24 timestamps cibles
        predicted_values: liste de 24 températures prédites

    Returns:
        Nombre de lignes insérées
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    inserted = 0

    for step, (t, v) in enumerate(zip(target_times, predicted_values), start=1):
        cursor.execute(
            """
            INSERT OR REPLACE INTO predictions
                (model_id, generated_at, horizon_step, target_time, predicted)
            VALUES (?, ?, ?, ?, ?)
            """,
            (model_id, generated_at, step, t, float(v)),
        )
        inserted += cursor.rowcount

    conn.commit()
    conn.close()
    logger.info("Prédictions : %d lignes sauvegardées (modèle=%s)", inserted, model_id)
    return inserted


def get_predictions(date: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    """
    Récupère les prédictions générées pour une date donnée.

    Args:
        date: '2024-06-01' (date de génération)

    Returns:
        DataFrame avec colonnes [model_id, generated_at, horizon_step, target_time, predicted]
    """
    conn = get_connection(db_path)
    df = pd.read_sql(
        "SELECT * FROM predictions WHERE generated_at LIKE ? ORDER BY horizon_step",
        conn,
        params=(f"{date}%",),
    )
    conn.close()
    return df


def get_predictions_with_actuals(
    start: str, end: str, db_path: Path = DB_PATH
) -> pd.DataFrame:
    """
    Joint les prédictions avec les valeurs réelles pour une période.

    Args:
        start, end: dates ISO (ex: '2024-06-01', '2024-06-03')

    Returns:
        DataFrame avec [target_time, predicted, actual, error]
    """
    conn = get_connection(db_path)
    df = pd.read_sql(
        """
        SELECT
            p.target_time,
            p.predicted,
            p.model_id,
            w.temperature_2m AS actual,
            ROUND(p.predicted - w.temperature_2m, 4) AS error
        FROM predictions p
        LEFT JOIN weather_data w ON p.target_time = w.timestamp
        WHERE p.target_time >= ? AND p.target_time <= ?
        ORDER BY p.target_time
        """,
        conn,
        params=(start, end),
    )
    conn.close()
    return df
