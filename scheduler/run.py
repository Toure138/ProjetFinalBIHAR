"""
scheduler/run.py — Automatisation quotidienne fetch + predict.

Tourne en boucle dans son propre conteneur Docker.
Chaque jour à 01:00 UTC :
  1. python -m src.data.fetch_data  (récupère les dernières données)
  2. python -m src.inference.predict (génère les prévisions)

Lancement :
    python scheduler/run.py
"""

import logging
import subprocess
import sys
import time
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Heure cible d'exécution (UTC)
TARGET_HOUR   = 1   # 01:00 UTC chaque jour
CHECK_INTERVAL = 60  # vérifie toutes les 60 secondes


def run_step(cmd: list[str], name: str) -> bool:
    """Exécute une commande et retourne True si succès."""
    log.info("Lancement : %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        log.info("%s OK", name)
        if result.stdout.strip():
            log.info(result.stdout.strip())
        return True
    else:
        log.error("%s ERREUR (code %d)", name, result.returncode)
        log.error(result.stderr.strip())
        return False


def daily_pipeline():
    """Fetch données + génération prédictions pour aujourd'hui."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log.info("=== Pipeline quotidien démarré (%s) ===", today)

    # Étape 1 : récupérer les nouvelles données jusqu'à aujourd'hui
    ok = run_step(
        [sys.executable, "-m", "src.data.fetch_data", "--end", today],
        "fetch_data",
    )
    if not ok:
        log.error("Arrêt du pipeline (fetch_data a échoué).")
        return

    # Étape 2 : générer les prédictions pour aujourd'hui
    run_step(
        [sys.executable, "-m", "src.inference.predict", "--date", today],
        "predict",
    )

    log.info("=== Pipeline quotidien terminé ===")


def main():
    log.info("Scheduler démarré — pipeline à %02d:00 UTC chaque jour.", TARGET_HOUR)

    # Exécuter une première fois au démarrage du conteneur
    daily_pipeline()

    last_run_day = datetime.now(timezone.utc).day

    while True:
        time.sleep(CHECK_INTERVAL)
        now     = datetime.now(timezone.utc)
        today   = now.day

        # Déclencher si on est à l'heure cible et qu'on n'a pas encore tourné aujourd'hui
        if now.hour == TARGET_HOUR and today != last_run_day:
            daily_pipeline()
            last_run_day = today


if __name__ == "__main__":
    main()
