"""CLI unifiée : `school-photo-dl tma` et `school-photo-dl klassly`."""

import argparse
import sys

from school_photo_dl import __version__


def build_parser():
    """Construit le parser argparse avec les sous-commandes."""
    parser = argparse.ArgumentParser(
        prog="school-photo-dl",
        description="Téléchargeurs de photos pour plateformes scolaires françaises.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{tma,klassly}", required=True)
    sub.add_parser("tma", help="Télécharger depuis toutemonannee.com")
    sub.add_parser("klassly", help="Télécharger depuis fr.klass.ly")
    return parser


def main(argv=None):
    """Point d'entrée console."""
    args = build_parser().parse_args(argv)

    if args.command == "tma":
        from school_photo_dl.tma.scraper import main as tma_main
        tma_main()
        return 0

    if args.command == "klassly":
        from school_photo_dl.klassly.scraper import main as klassly_main
        klassly_main()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
