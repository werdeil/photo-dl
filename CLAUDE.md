# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Python package (`school-photo-dl` on PyPI, import name `school_photo_dl`) exposant
des scrapers pour deux plateformes de partage photo scolaires françaises :
- [toutemonannee.com](https://www.toutemonannee.com) — [src/school_photo_dl/tma/scraper.py](src/school_photo_dl/tma/scraper.py)
- [klass.ly](https://fr.klass.ly) — [src/school_photo_dl/klassly/scraper.py](src/school_photo_dl/klassly/scraper.py)

Les deux pilotent Chrome via Selenium et enregistrent les images localement,
organisées par album/classe et date.

## Repo layout

```
src/school_photo_dl/
  __init__.py        # __version__
  cli.py             # entry point `school-photo-dl tma|klassly`
  shared/{driver,utils}.py
  tma/scraper.py
  klassly/scraper.py
tests/test_smoke.py
pyproject.toml       # métadonnées PyPI, deps, entry point, GPL-3.0
LICENSE              # GPL-3.0
.github/workflows/   # pylint, test (matrix 3.10-3.13), publish (tag v* → PyPI Trusted Publisher)
```

src/ layout : pour développer en local il **faut** une install éditable
(`pip install -e ".[dev]"`), sinon les imports `school_photo_dl.*` échouent.

## Setup

```bash
source .venv/bin/activate          # Python 3.13 déjà configuré
pip install -e ".[dev]"            # éditable + outils dev (pytest, build, twine, pylint)
```

Auth via `.env` à la racine (voir [.env.example](.env.example)) :

```bash
TMA_USERNAME="email@example.com"
TMA_PASSWORD="motdepasse"
TMA_DOWNLOAD_DIR="/chemin/vers/dossier"
TMA_HEADLESS="true"

KLASSLY_USERNAME="+33600000000"
KLASSLY_PASSWORD="motdepasse"
KLASSLY_DOWNLOAD_DIR="/chemin/vers/dossier"
KLASSLY_HEADLESS="true"
```

Dépendances déclarées dans [pyproject.toml](pyproject.toml) (pas de `requirements.txt`).
Packages clés : `selenium>=4.33`, `requests>=2.32`, `webdriver-manager>=4.0`,
`beautifulsoup4>=4.13`, `python-dotenv>=1.0`.

## Running

CLI unifiée installée par `pip install` :

```bash
school-photo-dl tma           # toutemonannee.com
school-photo-dl klassly       # klass.ly
school-photo-dl --version
```

Pour exécuter sans installer (dev) :

```bash
python -m school_photo_dl.cli tma
python -m school_photo_dl.tma.scraper       # direct module run
python -m school_photo_dl.klassly.scraper
```

Tests :

```bash
pytest                 # tests fumigènes : import package, parse CLI, safe_name
```

Build / publish manuel :

```bash
python -m build        # → dist/*.whl + *.tar.gz
twine check dist/*
# Publication : push d'un tag `vX.Y.Z` déclenche .github/workflows/publish.yml
```

TMA downloads vers `TMA_DOWNLOAD_DIR`, organisés en `{space_name}/{date} - {title}/`.
Klassly downloads vers `KLASSLY_DOWNLOAD_DIR`, organisés en `{class_name}/{YYYY-MM-DD} - {post_text}/`.

## Architecture

### Flow dans `src/school_photo_dl/tma/scraper.py`

```
main()                                # charge .env + configure logging ici (pas au module level)
  └─ get_session_cookie()             → login Selenium → cookie diedm_session
  └─ get_spaces()                     → HTTP API call → tous les albums/années ("spaces")
  └─ process_space(driver, space, base_download_dir, session_cookie)
       └─ scroll_to_load_all_articles()
       └─ collect_article_data()      → (date, title, post_url) par article
       └─ process_post()              → ouvre galerie, paginer, télécharger
            └─ download_image()       → HTTP GET + file write
```

### Key implementation details (TMA)

- **Auth**: `get_session_cookie()` → `login_with_credentials()` ouvre Chrome, remplit le formulaire en deux étapes (email → "Continuer" → password → "Je me connecte") et retourne le cookie `diedm_session`. Cookie injecté dans `requests` et le driver Selenium.
- **Image URL normalization**: URLs contenant `"thumbs"` réécrites vers `"hd"` ; query strings strippées.
- **Carousel pagination**: les articles peuvent avoir >25 ou >50 images ; `_handle_gallery_images()` clique les contrôles "page précédente" pour les deux cas.
- **Fallback sans galerie**: `_handle_fallback_images()` scanne `<img>`, `background-image` et `data-src` quand la galerie ne s'ouvre pas.
- **Output path**: `TMA_DOWNLOAD_DIR` (obligatoire, lève `EnvironmentError`) ; lu dans `main()`, **pas** au niveau module (sinon `import school_photo_dl.tma` planterait sans `.env`).

### Flow dans `src/school_photo_dl/klassly/scraper.py`

```
main()                                # charge .env + configure logging ici
  └─ login()                          → Selenium remplit tel+password → klassroom_token
  └─ get_classes()                    → navigue /class, capture app.connect via CDP → classes
  └─ process_class(driver, klass, download_dir)
       └─ collect_all_posts()         → boucle CDP klass.history jusqu'à épuisement
       └─ process_post()              → télécharge les attachments image du post
            └─ download_image()       → Selenium navigue + Network.getResponseBody CDP
```

### Key implementation details (Klassly)

- **Auth**: formulaire en une étape (tel + password ensemble) → `button.kr-login-form__btn` ; cookie `klassroom_token` récupéré.
- **Classes**: extraites du champ `klasses` de `app.connect` capturé via CDP lors de la navigation `/class`.
- **Posts**: `klass.history` capturé via CDP pendant scroll ; dict keyed par postID avec `attachments` embarqués.
- **Image download**: `www.klass.ly` et `data.klassroom.co` bloquent Python `requests` (403) mais acceptent Chrome → on navigue avec le driver puis on récupère le corps via `Network.getResponseBody`. URLs normalisées de `data.klassroom.co/img/` vers `www.klass.ly/_data/img/`.
- **Output path**: `KLASSLY_DOWNLOAD_DIR` (obligatoire) ; lu dans `main()`. `KLASSLY_HEADLESS=false` pour mode visible.

### Shared

- `shared/driver.py` — `init_driver(headless=True, enable_cdp=False)` ; CDP requis pour Klassly.
- `shared/utils.py` — `configure_logging()` (INFO + horodatage), `safe_name()` (nettoie les caractères interdits dans les noms de fichier).

## Convention

- Logging Python `logging` au niveau INFO, stdout uniquement.
- Aucune lecture de variable d'env au niveau module — toujours dans `main()` — pour que `import school_photo_dl.*` reste sûr sans `.env`.
- Pas de `requirements.txt` : ajouter une dép = éditer `[project.dependencies]` dans `pyproject.toml`.
