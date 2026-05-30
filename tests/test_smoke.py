"""Tests fumigènes : import du package et de la CLI."""


def test_package_importable():
    import school_photo_dl

    assert school_photo_dl.__version__


def test_cli_parser_builds():
    from school_photo_dl.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["tma"])
    assert args.command == "tma"
    args = parser.parse_args(["klassly"])
    assert args.command == "klassly"


def test_safe_name():
    from school_photo_dl.shared.utils import safe_name

    assert safe_name("hello/world") == "hello_world"
    assert safe_name('a:b"c|d') == "a_b_c_d"
