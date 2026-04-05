"""
report.py — Monitoring : comparaison prédictions vs valeurs réelles.

Génère un graphique et un tableau de métriques d'erreur,
sauvegardés dans monitoring/output/.

Usage :
    python -m src.monitoring.report --start 2026-12-01 --end 2024-12-31
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from src.common.config import MONITORING_DIR
from src.common.database import get_predictions_with_actuals, init_db
from src.common.logger import get_logger

logger = get_logger(__name__)


def generate_report(start: str, end: str) -> dict:
    """
    Génère le graphique et les métriques pour une période donnée.

    Args:
        start: 'YYYY-MM-DD'
        end:   'YYYY-MM-DD'

    Returns:
        dict avec les métriques {mae, rmse, n_points}
    """
    init_db()
    MONITORING_DIR.mkdir(parents=True, exist_ok=True)

    # ── Données ───────────────────────────────────────────────────────────────
    df = get_predictions_with_actuals(start, end)

    if df.empty:
        logger.warning("Aucune donnée disponible pour %s → %s", start, end)
        return {}

    # Garder uniquement les lignes où on a les deux (prédit + réel)
    df_clean = df.dropna(subset=["predicted", "actual"])
    n = len(df_clean)
    logger.info("Comparaison : %d points avec prédictions ET réel", n)

    if n == 0:
        logger.warning("Aucun point n'a à la fois une prédiction et une valeur réelle.")
        return {}

    # ── Métriques ─────────────────────────────────────────────────────────────
    mae  = mean_absolute_error(df_clean["actual"], df_clean["predicted"])
    rmse = np.sqrt(mean_squared_error(df_clean["actual"], df_clean["predicted"]))
    bias = (df_clean["predicted"] - df_clean["actual"]).mean()

    metrics = {"mae": round(mae, 4), "rmse": round(rmse, 4),
               "bias": round(bias, 4), "n_points": n}

    logger.info("Métriques monitoring → MAE=%.4f  RMSE=%.4f  Biais=%.4f",
                mae, rmse, bias)

    # ── Graphique ─────────────────────────────────────────────────────────────
    df_clean = df_clean.copy()
    df_clean["target_time"] = pd.to_datetime(df_clean["target_time"])
    df_clean = df_clean.sort_values("target_time")

    fig, axes = plt.subplots(2, 1, figsize=(14, 8))

    # Panneau 1 : prédictions vs réel
    axes[0].plot(df_clean["target_time"], df_clean["actual"],
                 "k-", linewidth=1.5, alpha=0.8, label="Réel")
    axes[0].plot(df_clean["target_time"], df_clean["predicted"],
                 "b--", linewidth=1.2, alpha=0.8, label="Prédit")
    axes[0].set_title(
        f"Prédictions vs Réel  |  MAE={mae:.3f}°C  RMSE={rmse:.3f}°C  ({start} → {end})"
    )
    axes[0].set_ylabel("Température (°C)")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Panneau 2 : erreur (prédit - réel)
    axes[1].bar(df_clean["target_time"], df_clean["error"],
                color=df_clean["error"].apply(lambda e: "tomato" if e > 0 else "steelblue"),
                alpha=0.7, width=0.1)
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].axhline(bias, color="orange", linewidth=1.2, linestyle="--",
                    label=f"Biais moyen = {bias:.3f}°C")
    axes[1].set_title("Erreur = Prédit − Réel")
    axes[1].set_ylabel("Erreur (°C)")
    axes[1].set_xlabel("Date")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()

    # Sauvegarde
    out_path = MONITORING_DIR / f"report_{start}_{end}.png"
    plt.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close()
    logger.info("Graphique sauvegardé : %s", out_path)

    # ── Tableau texte ─────────────────────────────────────────────────────────
    print("\n=== Rapport de monitoring ===")
    print(f"Période   : {start} → {end}")
    print(f"Points    : {n}")
    print(f"MAE       : {mae:.4f} °C")
    print(f"RMSE      : {rmse:.4f} °C")
    print(f"Biais     : {bias:.4f} °C")
    print(f"Graphique : {out_path}\n")

    return metrics


# ─── Point d'entrée CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Génère le rapport de monitoring")
    parser.add_argument("--start", required=True, help="Date de début YYYY-MM-DD")
    parser.add_argument("--end",   required=True, help="Date de fin   YYYY-MM-DD")
    args = parser.parse_args()

    generate_report(args.start, args.end)
