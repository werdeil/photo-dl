"""Tests fumigènes : import du package et de la CLI."""

from datetime import datetime

from school_photo_dl.cli import build_parser
from school_photo_dl.klassly.scraper import _post_naming
from school_photo_dl.shared.utils import (
    build_name_prefix,
    first_sentence,
    parse_french_date,
    safe_name,
    slugify,
)
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
    args = parser.parse_args(["config"])
    assert args.command == "config"


def test_cli_parser_no_command_is_auto_mode():
    """Sans sous-commande, command vaut None (mode auto basé sur .env)."""
    parser = build_parser()
    args = parser.parse_args([])
    assert args.command is None


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


def test_slugify_lowercases_and_strips_accents():
    """slugify enlève accents, espaces et caractères spéciaux."""
    assert slugify("Sortie au musée") == "sortie-au-musee"
    assert slugify("Kermesse de fin d'année !") == "kermesse-de-fin-d-annee"
    assert slugify("") == ""
    assert slugify("   ") == ""


def test_slugify_truncates():
    """slugify tronque proprement et n'expose pas de tiret final."""
    long_text = "a" * 30 + " " + "b" * 30
    out = slugify(long_text, max_len=40)
    assert len(out) <= 40
    assert not out.endswith("-")


def test_build_name_prefix_combines_or_falls_back():
    """Combine date+slug ; sinon retourne celui qui existe ; vide si rien."""
    assert build_name_prefix("2025-03-15", "sortie") == "2025-03-15_sortie"
    assert build_name_prefix("2025-03-15", "") == "2025-03-15"
    assert build_name_prefix("", "sortie") == "sortie"
    assert build_name_prefix("", "") == ""


def test_post_naming_klassly_nominal():
    """Post klassly avec date et texte → dossier ISO + préfixe slug."""
    # 1710500400 = 2024-03-15 09:20:00 UTC, soit dans la journée locale
    post = {"date": 1710500400000, "text": "Sortie au musée"}
    folder, prefix, base_dt = _post_naming("PID", post)
    assert folder.startswith("2024-03-15 - ")
    assert "Sortie au mus" in folder
    assert prefix == "2024-03-15_sortie-au-musee"
    assert base_dt is not None


def test_post_naming_klassly_no_text_falls_back_to_post_id():
    """Post sans texte → dossier '… - {post_id}', préfixe = juste la date."""
    post = {"date": 1710500400000}
    folder, prefix, _ = _post_naming("PID42", post)
    assert folder.endswith(" - PID42")
    assert prefix == "2024-03-15"


def test_post_naming_klassly_no_date():
    """Post sans date → dossier 'unknown - …', préfixe = juste le slug."""
    post = {"text": "Kermesse"}
    folder, prefix, base_dt = _post_naming("PID", post)
    assert folder.startswith("unknown - ")
    assert prefix == "kermesse"
    assert base_dt is None


def test_first_sentence_takes_first_line():
    """first_sentence prend la première ligne non vide."""
    assert first_sentence("\n\nPremière ligne\nSeconde ligne") == "Première ligne"


def test_first_sentence_cuts_at_punctuation():
    """first_sentence coupe à `.`, `!` ou `?`."""
    assert first_sentence("Bonjour le monde. Et la suite.") == "Bonjour le monde"
    assert first_sentence("Super sortie ! On a vu plein de choses.") == "Super sortie"
    assert first_sentence("Vraiment ? Oui.") == "Vraiment"


def test_first_sentence_truncates():
    """first_sentence tronque à max_len sans phrase terminale."""
    assert first_sentence("a" * 100, max_len=20) == "a" * 20


def test_first_sentence_empty():
    """first_sentence retourne '' pour entrée vide ou whitespace."""
    assert first_sentence("") == ""
    assert first_sentence("   \n  \n") == ""


def test_post_naming_klassly_multiline_takes_first_sentence():
    """Post multi-lignes → dossier basé sur la première phrase."""
    post = {
        "date": 1710500400000,
        "text": (
            "Sortie au musée d'Orsay. Voici les photos prises par les enfants.\n"
            "Merci aux parents."
        ),
    }
    folder, prefix, _ = _post_naming("PID", post)
    assert folder == "2024-03-15 - Sortie au musée d'Orsay"
    assert prefix == "2024-03-15_sortie-au-musee-d-orsay"
