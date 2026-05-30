"""Utilitaires partagés entre les scrapers."""

import logging
import os
import re
import unicodedata
from datetime import datetime

logger = logging.getLogger(__name__)


FRENCH_MONTHS = {
    "janvier": 1, "janv": 1, "jan": 1,
    "février": 2, "fevrier": 2, "févr": 2, "fevr": 2, "fév": 2, "fev": 2,
    "mars": 3, "mar": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7, "juil": 7, "jul": 7,
    "août": 8, "aout": 8,
    "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "décembre": 12, "decembre": 12, "déc": 12, "dec": 12,
}


def configure_logging():
    """Configure le logging au niveau INFO avec horodatage."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def safe_name(name):
    """Remplace les caractères interdits dans un nom de fichier/dossier."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip()


def build_name_prefix(iso_date, title_slug):
    """Combine `YYYY-MM-DD` et un slug en préfixe `YYYY-MM-DD_slug`.

    Si l'un manque, retourne l'autre. Si les deux manquent, retourne `""`.
    """
    if iso_date and title_slug:
        return f"{iso_date}_{title_slug}"
    return iso_date or title_slug


def slugify(text, max_len=40):
    """Convertit un texte en slug ASCII portable.

    Minuscules, accents supprimés, tout caractère non alphanumérique remplacé
    par un tiret. Retourne une chaîne vide si l'entrée est vide ou ne contient
    aucun caractère exploitable.
    """
    if not text:
        return ""
    ascii_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', ascii_text).strip('-').lower()
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip('-')
    return slug


def parse_french_date(date_str, years_range, default_hour=10):
    """Parse une date FR ('12 mai') + une plage d'années ('2024-2025') en datetime.

    Règle: si le mois est entre septembre et décembre, on prend l'année de début ;
    sinon l'année de fin. Renvoie None si la date n'est pas parsable.
    """
    if not date_str:
        return None
    parts = date_str.strip().lower().split()
    if len(parts) < 2:
        return None
    try:
        day = int(parts[0])
    except ValueError:
        return None
    month_key = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ]", "", parts[1])
    month = FRENCH_MONTHS.get(month_key)
    if not month:
        return None
    years = re.findall(r"\d{4}", years_range or "")
    if len(years) >= 2:
        start, end = int(years[0]), int(years[1])
    elif len(years) == 1:
        start = end = int(years[0])
    else:
        start = end = datetime.now().year
    year = start if month >= 9 else end
    try:
        return datetime(year, month, day, default_hour, 0, 0)
    except ValueError:
        return None


def set_image_datetime(path, dt):
    """Écrit DateTimeOriginal en EXIF et met à jour le mtime du fichier.

    L'écriture EXIF est best-effort : si le format ne le supporte pas
    (GIF, parfois WebP), on logge en debug et le mtime reste appliqué.
    """
    if dt is None or not os.path.exists(path):
        return
    ts_str = dt.strftime("%Y:%m:%d %H:%M:%S")
    try:
        # pylint: disable=import-outside-toplevel
        from PIL import Image
        with Image.open(path) as img:
            fmt = img.format
            exif = img.getexif()
            exif[36867] = ts_str  # DateTimeOriginal
            exif[36868] = ts_str  # DateTimeDigitized
            exif[306] = ts_str    # DateTime
            save_kwargs = {"exif": exif, "format": fmt}
            if fmt == "JPEG":
                save_kwargs["quality"] = "keep"
            img.save(path, **save_kwargs)
    except Exception as err:  # pylint: disable=broad-except
        logger.debug("EXIF non écrit pour %s : %s", os.path.basename(path), err)
    epoch = dt.timestamp()
    try:
        os.utime(path, (epoch, epoch))
    except OSError as err:
        logger.debug("mtime non mis à jour pour %s : %s", os.path.basename(path), err)
