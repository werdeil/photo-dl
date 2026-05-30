"""Tests fumigènes : import du package et de la CLI."""

from datetime import datetime

from school_photo_dl.cli import build_parser
from school_photo_dl.shared.utils import parse_french_date, safe_name


def test_package_importable():
    """Le package doit être importable et exposer __version__."""
    # pylint: disable=import-outside-toplevel  # import testé localement
    import school_photo_dl

    assert school_photo_dl.__version__


def test_cli_parser_builds():
    """Le parser argparse expose les sous-commandes tma et klassly."""
    parser = build_parser()
    args = parser.parse_args(["tma"])
    assert args.command == "tma"
    args = parser.parse_args(["klassly"])
    assert args.command == "klassly"


def test_safe_name():
    """safe_name remplace les caractères interdits par des underscores."""
    assert safe_name("hello/world") == "hello_world"
    assert safe_name('a:b"c|d') == "a_b_c_d"


def test_parse_french_date_spring_uses_end_year():
    """'12 mai' avec '2024-2025' tombe au printemps → année de fin."""
    assert parse_french_date("12 mai", "2024-2025") == datetime(2025, 5, 12, 10, 0, 0)


def test_parse_french_date_autumn_uses_start_year():
    """'3 octobre' avec '2024-2025' tombe à l'automne → année de début."""
    assert parse_french_date("3 octobre", "2024-2025") == datetime(2024, 10, 3, 10, 0, 0)


def test_parse_french_date_handles_abbreviations_and_accents():
    """Les abréviations et accents sont reconnus."""
    assert parse_french_date("8 févr.", "2024-2025") == datetime(2025, 2, 8, 10, 0, 0)
    assert parse_french_date("15 déc", "2024-2025") == datetime(2024, 12, 15, 10, 0, 0)


def test_parse_french_date_returns_none_on_garbage():
    """Une date non parsable retourne None."""
    assert parse_french_date("", "2024-2025") is None
    assert parse_french_date("unknown", "2024-2025") is None
    assert parse_french_date("32 mai", "2024-2025") is None
