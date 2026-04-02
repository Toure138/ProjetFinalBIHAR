"""
logger.py — Logging structuré du projet.

Utilise le module standard `logging` de Python.
Chaque module récupère son logger via get_logger(__name__).
Format : timestamp | niveau | module | message
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Retourne un logger configuré pour le module donné.

    Args:
        name: nom du module (utiliser __name__ à l'appel)

    Returns:
        logging.Logger configuré avec handler console + niveau INFO
    """
    logger = logging.getLogger(name)

    # Éviter d'ajouter plusieurs handlers si appelé plusieurs fois
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── Handler console (stdout) ───────────────────────────────────────────────
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
