"""Utilitaires partagés entre les scrapers."""

import logging
import re


def configure_logging():
    """Configure le logging au niveau INFO avec horodatage."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def safe_name(name):
    """Remplace les caractères interdits dans un nom de fichier/dossier."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip()
