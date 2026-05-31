"""CLI unifiée : `school-photo-dl tma` et `school-photo-dl klassly`.

Sans sous-commande, lit `.env` et lance en séquence toutes les plateformes pour
lesquelles des identifiants sont configurés.
"""

import argparse
import logging
import os
import sys

from school_photo_dl import __version__
from school_photo_dl.shared.utils import configure_logging


def build_parser():
    """Construit le parser argparse avec les sous-commandes."""
    parser = argparse.ArgumentParser(
        prog="school-photo-dl",
        description="Téléchargeur de photos pour plateformes scolaires françaises. "
        "Sans sous-commande, lance les plateformes configurées dans .env.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{config,tma,klassly}")
    sub.add_parser("config", help="Configurer le fichier .env de façon interactive")
    sub.add_parser("tma", help="Télécharger depuis toutemonannee.com")
    sub.add_parser("klassly", help="Télécharger depuis fr.klass.ly")
    return parser


# Variables d'environnement requises par plateforme (DOWNLOAD_DIR partagé inclus).
_REQUIRED_ENV = {
    "tma": ("DOWNLOAD_DIR", "TMA_USERNAME", "TMA_PASSWORD"),
    "klassly": ("DOWNLOAD_DIR", "KLASSLY_USERNAME", "KLASSLY_PASSWORD"),
}


def _ensure_configured(platform):
    """Vérifie les variables requises ; lance `config` si certaines manquent.

    Retourne True si la plateforme est prête à tourner, False si l'utilisateur n'a
    finalement pas renseigné tout le nécessaire.
    """
    # pylint: disable=import-outside-toplevel  # lazy: dotenv pas requis pour `config`
    from dotenv import load_dotenv
    load_dotenv()

    missing = [k for k in _REQUIRED_ENV[platform] if not os.getenv(k)]
    if not missing:
        return True

    print(
        f"Configuration manquante pour '{platform}' ({', '.join(missing)}). "
        "Lancement de l'assistant de configuration.\n",
        file=sys.stderr,
    )
    from school_photo_dl.config_cmd import run_config
    run_config()
    # Recharge le .env fraîchement écrit en écrasant les valeurs déjà en mémoire.
    load_dotenv(override=True)

    still_missing = [k for k in _REQUIRED_ENV[platform] if not os.getenv(k)]
    if still_missing:
        print(
            f"Variables toujours manquantes : {', '.join(still_missing)}. "
            "Relancez la commande après avoir complété la configuration.",
            file=sys.stderr,
        )
        return False
    return True


def _run_tma():
    # pylint: disable=import-outside-toplevel  # lazy: n'importe pas le scraper klassly inutilement
    from school_photo_dl.tma.scraper import main as tma_main
    logging.info("Démarrage du scraper toutemonannee.com (TMA)")
    tma_main()


def _run_klassly():
    # pylint: disable=import-outside-toplevel  # lazy: n'importe pas le scraper tma inutilement
    from school_photo_dl.klassly.scraper import main as klassly_main
    logging.info("Démarrage du scraper fr.klass.ly (Klassly)")
    klassly_main()


def _detect_available_platforms():
    """Retourne la liste des plateformes dont les identifiants sont présents dans l'env."""
    # pylint: disable=import-outside-toplevel  # lazy: dotenv pas requis pour les sous-commandes explicites
    from dotenv import load_dotenv
    load_dotenv()

    available = []
    if os.getenv("TMA_USERNAME") and os.getenv("TMA_PASSWORD"):
        available.append("tma")
    if os.getenv("KLASSLY_USERNAME") and os.getenv("KLASSLY_PASSWORD"):
        available.append("klassly")
    return available


_RUNNERS = {"tma": _run_tma, "klassly": _run_klassly}


def _run_auto():
    """Détecte les plateformes configurées dans .env et les lance en séquence.

    Si aucune n'est détectée, lance l'assistant `config` puis redétecte. Chaque
    plateforme passe par `_ensure_configured` (qui vérifie aussi `DOWNLOAD_DIR`).
    """
    available = _detect_available_platforms()
    if not available:
        print(
            "Aucune plateforme configurée. Lancement de l'assistant de configuration.\n",
            file=sys.stderr,
        )
        # pylint: disable=import-outside-toplevel  # lazy: pas besoin du module hors de ce cas
        from school_photo_dl.config_cmd import run_config
        from dotenv import load_dotenv
        run_config()
        load_dotenv(override=True)
        available = _detect_available_platforms()
        if not available:
            print(
                "Toujours aucune plateforme configurée : renseignez les identifiants "
                "TMA et/ou Klassly. Abandon.",
                file=sys.stderr,
            )
            return 1

    skipped = [p for p in _REQUIRED_ENV if p not in available]
    msg = f"Mode auto : à traiter → {', '.join(available)}"
    if skipped:
        msg += f" | ignoré (identifiants absents) → {', '.join(skipped)}"
    logging.info(msg)
    exit_code = 0
    for platform in available:
        if not _ensure_configured(platform):
            exit_code = 1
            continue
        _RUNNERS[platform]()
    return exit_code


def main(argv=None):
    """Point d'entrée console."""
    configure_logging()
    args = build_parser().parse_args(argv)

    if args.command is None:
        return _run_auto()

    if args.command == "config":
        # pylint: disable=import-outside-toplevel  # lazy: pas besoin du module pour les autres commandes
        from school_photo_dl.config_cmd import run_config
        return run_config()

    if args.command in _RUNNERS:
        if not _ensure_configured(args.command):
            return 1
        _RUNNERS[args.command]()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
