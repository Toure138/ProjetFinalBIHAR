"""
fetch_data.py — Téléchargement des données météo depuis Open-Meteo.

Flux :
  1. Appel à l'API Open-Meteo (données horaires)
  2. Agrégation en pas de 3h (moyenne sur blocs 00–02, 03–05, ...)
  3. Sauvegarde dans la table weather_data de SQLite

Usage :
    python -m src.data.fetch_data --end 2025-01-31
    python -m src.data.fetch_data --start 2024-01-01 --end 2024-12-31
"""

import argparse
from datetime import date, timedelta

import pandas as pd
import requests

from src.common.config import DB_PATH, LATITUDE, LONGITUDE, TIMEZONE, VARIABLE
from src.common.database import init_db, insert_weather_safe
from src.common.logger import get_logger

logger = get_logger(__name__)

# URL de base de l'API Open-Meteo (données historiques gratuites)
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_hourly(start: str, end: str) -> pd.DataFrame:
    """
    Télécharge les données horaires depuis Open-Meteo.

    Args:
        start: date de début 'YYYY-MM-DD'
        end:   date de fin   'YYYY-MM-DD'

    Returns:
        DataFrame avec colonnes ['date', 'temperature_2m'] à pas horaire
    """
    params = {
        "latitude":     LATITUDE,
        "longitude":    LONGITUDE,
        "start_date":   start,
        "end_date":     end,
        "hourly":       VARIABLE,
        "timezone":     TIMEZONE,
    }

    logger.info("Téléchargement Open-Meteo : %s → %s", start, end)
    response = requests.get(OPENMETEO_URL, params=params, timeout=30)
    response.raise_for_status()   # lève une exception si HTTP 4xx/5xx

    data = response.json()

    df = pd.DataFrame({
        "date":           pd.to_datetime(data["hourly"]["time"]),
        "temperature_2m": data["hourly"][VARIABLE],
    })

    # Supprimer les éventuelles valeurs manquantes
    df = df.dropna(subset=["temperature_2m"])
    logger.info("Données horaires téléchargées : %d enregistrements", len(df))
    return df


def aggregate_3h(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège la série horaire en pas de 3h.

    Règle : la valeur à 00h = moyenne de 00h, 01h, 02h ;
            la valeur à 03h = moyenne de 03h, 04h, 05h ; etc.

    Args:
        df_hourly: DataFrame horaire avec colonnes ['date', 'temperature_2m']

    Returns:
        DataFrame agrégé avec colonnes ['timestamp', 'temperature_2m']
    """
    df = (
        df_hourly
        .sort_values("date")
        .set_index("date")
        .resample("3h", label="left", closed="left")   # pandas >= 2.2 : minuscule
        .mean(numeric_only=True)
        .reset_index()
        .rename(columns={"date": "timestamp"})
    )

    # Formater le timestamp comme chaîne ISO sans fuseau horaire
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M")
    logger.info("Agrégation 3h : %d pas de temps", len(df))
    return df


def fetch_and_store(start: str, end: str) -> int:
    """
    Pipeline complet : téléchargement → agrégation → sauvegarde SQLite.

    Args:
        start: 'YYYY-MM-DD'
        end:   'YYYY-MM-DD'

    Returns:
        Nombre de nouvelles lignes insérées
    """
    init_db()

    df_hourly = fetch_hourly(start, end)
    df_3h     = aggregate_3h(df_hourly)
    inserted  = insert_weather_safe(df_3h)

    logger.info("Pipeline fetch_and_store terminé : %d nouvelles lignes", inserted)
    return inserted


# ─── Point d'entrée CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Télécharge les données météo Open-Meteo")
    parser.add_argument(
        "--start", default="2023-01-01",
        help="Date de début YYYY-MM-DD (défaut: 2023-01-01)"
    )
    parser.add_argument(
        "--end", default=str(date.today() - timedelta(days=1)),
        help="Date de fin YYYY-MM-DD (défaut: hier)"
    )
    args = parser.parse_args()

    n = fetch_and_store(args.start, args.end)
    print(f"✓ {n} nouvelles lignes insérées dans {DB_PATH}")
