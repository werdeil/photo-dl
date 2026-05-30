"""CLI unifiée : `school-photo-dl tma` et `school-photo-dl klassly`.

Sans sous-commande, lit `.env` et lance en séquence toutes les plateformes pour
lesquelles des identifiants sont configurés.
"""

import argparse
import logging
import os
import sys

from school_photo_dl import __version__


def build_parser():
    """Construit le parser argparse avec les sous-commandes."""
    parser = argparse.ArgumentParser(
        prog="school-photo-dl",
        description="Téléchargeurs de photos pour plateformes scolaires françaises. "
        "Sans sous-commande, lance les plateformes configurées dans .env.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{tma,klassly}")
    sub.add_parser("tma", help="Télécharger depuis toutemonannee.com")
    sub.add_parser("klassly", help="Télécharger depuis fr.klass.ly")
    return parser


def _run_tma():
    # pylint: disable=import-outside-toplevel  # lazy: n'importe pas le scraper klassly inutilement
    from school_photo_dl.tma.scraper import main as tma_main
    tma_main()


def _run_klassly():
    # pylint: disable=import-outside-toplevel  # lazy: n'importe pas le scraper tma inutilement
    from school_photo_dl.klassly.scraper import main as klassly_main
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


def _run_auto():
    """Détecte les plateformes configurées dans .env et les lance en séquence."""
    available = _detect_available_platforms()
    if not available:
        print(
            "Aucune plateforme configurée : renseignez TMA_USERNAME/TMA_PASSWORD "
            "et/ou KLASSLY_USERNAME/KLASSLY_PASSWORD dans .env.",
            file=sys.stderr,
        )
        return 1

    logging.info("Mode auto : exécution séquentielle de %s", ", ".join(available))
    for platform in available:
        if platform == "tma":
            _run_tma()
        elif platform == "klassly":
            _run_klassly()
    return 0


def main(argv=None):
    """Point d'entrée console."""
    args = build_parser().parse_args(argv)

    if args.command is None:
        return _run_auto()

    if args.command == "tma":
        _run_tma()
        return 0

    if args.command == "klassly":
        _run_klassly()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
