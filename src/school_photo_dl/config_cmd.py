"""Commande `school-photo-dl config` : génère/édite le fichier `.env` interactivement.

Pose une série de questions à l'utilisateur (avec les valeurs actuelles comme
défauts si un `.env` existe déjà) et écrit le fichier au format attendu par les
scrapers. Les mots de passe sont saisis sans écho via `getpass`.
"""

import getpass
import os
from pathlib import Path

# Valeur par défaut proposée pour DOWNLOAD_DIR si rien n'est déjà configuré.
_DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Photos" / "school-photo-dl")

# Ordre et présentation des sections, calqué sur .env.example.
_TEMPLATE = """# --- Partagé ---
DOWNLOAD_DIR={DOWNLOAD_DIR}
# Ouvre le navigateur visuellement si "false" (défaut : "true")
HEADLESS={HEADLESS}

# --- toutemonannee.com ---
TMA_USERNAME={TMA_USERNAME}
TMA_PASSWORD={TMA_PASSWORD}

# --- fr.klass.ly ---
KLASSLY_USERNAME={KLASSLY_USERNAME}
KLASSLY_PASSWORD={KLASSLY_PASSWORD}
"""

_KEYS = (
    "DOWNLOAD_DIR",
    "HEADLESS",
    "TMA_USERNAME",
    "TMA_PASSWORD",
    "KLASSLY_USERNAME",
    "KLASSLY_PASSWORD",
)


def _env_path():
    """Retourne le chemin du `.env` à la racine du projet (cwd)."""
    return Path.cwd() / ".env"


def _read_existing(path):
    """Parse un `.env` existant en dict clé→valeur (best effort)."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _prompt(label, current, *, secret=False):
    """Demande une valeur ; Entrée conserve la valeur actuelle."""
    if secret:
        suffix = " [inchangé]" if current else ""
        entered = getpass.getpass(f"{label}{suffix} : ")
        return entered if entered else current
    suffix = f" [{current}]" if current else ""
    entered = input(f"{label}{suffix} : ").strip()
    return entered if entered else current


def run_config():
    """Interroge l'utilisateur et écrit le fichier `.env`. Retourne un code de sortie."""
    path = _env_path()
    current = _read_existing(path)

    if path.exists():
        print(f"Fichier existant détecté : {path}")
        print("Entrée vide = conserver la valeur actuelle.\n")
    else:
        print(f"Création de {path}")
        print("Entrée vide = laisser vide.\n")

    values = dict.fromkeys(_KEYS, "")
    values.update({k: current.get(k, "") for k in _KEYS})

    print("--- Partagé ---")
    values["DOWNLOAD_DIR"] = _prompt(
        "Dossier de téléchargement (DOWNLOAD_DIR)",
        values["DOWNLOAD_DIR"] or _DEFAULT_DOWNLOAD_DIR,
    )
    headless = _prompt(
        "Mode navigateur invisible ? true/false (HEADLESS)",
        values["HEADLESS"] or "true",
    ).lower()
    values["HEADLESS"] = "false" if headless in ("false", "f", "non", "no", "n") else "true"

    print("\n--- toutemonannee.com (laisser vide pour ignorer) ---")
    values["TMA_USERNAME"] = _prompt("Email TMA (TMA_USERNAME)", values["TMA_USERNAME"])
    values["TMA_PASSWORD"] = _prompt(
        "Mot de passe TMA (TMA_PASSWORD)", values["TMA_PASSWORD"], secret=True
    )

    print("\n--- fr.klass.ly (laisser vide pour ignorer) ---")
    values["KLASSLY_USERNAME"] = _prompt(
        "Téléphone Klassly, ex +33600000000 (KLASSLY_USERNAME)", values["KLASSLY_USERNAME"]
    )
    values["KLASSLY_PASSWORD"] = _prompt(
        "Mot de passe Klassly (KLASSLY_PASSWORD)", values["KLASSLY_PASSWORD"], secret=True
    )

    path.write_text(_TEMPLATE.format(**values), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # permissions best effort (ex. Windows)

    print(f"\n✓ Configuration enregistrée dans {path}")
    if not values["DOWNLOAD_DIR"]:
        print("⚠ DOWNLOAD_DIR est vide : les scrapers échoueront tant qu'il n'est pas renseigné.")
    return 0
