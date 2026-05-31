# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Python package (`school-photo-dl` on PyPI, import name `school_photo_dl`) exposant
des scrapers pour deux plateformes de partage photo scolaires françaises :
- [toutemonannee.com](https://www.toutemonannee.com) — [src/school_photo_dl/tma/scraper.py](src/school_photo_dl/tma/scraper.py)
- [klass.ly](https://fr.klass.ly) — [src/school_photo_dl/klassly/scraper.py](src/school_photo_dl/klassly/scraper.py)

Les deux ouvrent Chrome via Selenium pour l'authentification ; ensuite TMA
récupère les photos via une API JSON (`requests` pur), tandis que Klassly
combine `requests` + fetch JS injecté dans la page + fallback CDP. Tout est
enregistré localement, organisé par album/classe et date.

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
# Partagé
DOWNLOAD_DIR="/chemin/vers/dossier"
HEADLESS="true"

# toutemonannee.com
TMA_USERNAME="email@example.com"
TMA_PASSWORD="motdepasse"

# fr.klass.ly
KLASSLY_USERNAME="+33600000000"
KLASSLY_PASSWORD="motdepasse"
```

Dépendances déclarées dans [pyproject.toml](pyproject.toml) (pas de `requirements.txt`).
Packages clés : `selenium>=4.33`, `requests>=2.32`, `webdriver-manager>=4.0`,
`Pillow>=10.0`, `python-dotenv>=1.0`.

## Running

CLI unifiée installée par `pip install` :

```bash
school-photo-dl config        # crée/édite .env interactivement (questions à l'utilisateur)
school-photo-dl tma           # toutemonannee.com
school-photo-dl klassly       # klass.ly
school-photo-dl               # auto : lit .env et enchaîne les plateformes configurées
school-photo-dl --version
```

La sous-commande `config` ([src/school_photo_dl/config_cmd.py](src/school_photo_dl/config_cmd.py))
`run_config()` lit le `.env` du cwd s'il existe (valeurs proposées comme défauts,
Entrée vide = inchangé ; `DOWNLOAD_DIR` défaut `~/Photos/school-photo-dl`), pose les
questions section par section (mots de passe via `getpass`, sans écho) et réécrit le
fichier au format de [.env.example](.env.example) avec permissions `0600`.

Les sous-commandes `tma`/`klassly` appellent `_ensure_configured(platform)` avant de
lancer le scraper : si une variable requise manque (`DOWNLOAD_DIR` + identifiants de la
plateforme), l'assistant `config` est lancé automatiquement, puis le `.env` est rechargé
(`load_dotenv(override=True)`). Si des variables manquent toujours, sortie code 1.

Mode auto (sans sous-commande) : [src/school_photo_dl/cli.py](src/school_photo_dl/cli.py)
`_run_auto()` charge `.env`, détecte les plateformes avec identifiants présents
(`TMA_USERNAME`/`TMA_PASSWORD`, `KLASSLY_USERNAME`/`KLASSLY_PASSWORD`) et appelle
les `main()` correspondants en séquence. Si **aucune** n'est détectée, lance
l'assistant `config`, recharge `.env` (`override=True`) et redétecte ; abandon code 1
s'il n'y a toujours rien. Chaque plateforme retenue passe ensuite par
`_ensure_configured` (qui vérifie aussi `DOWNLOAD_DIR` et relance `config` au besoin).

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

TMA downloads vers `DOWNLOAD_DIR`, organisés en `{space_name}/{date} - {title}/`.
Klassly downloads vers `DOWNLOAD_DIR`, organisés en `{class_name}/{YYYY-MM-DD} - {post_text}/`.

## Architecture

### Flow dans `src/school_photo_dl/tma/scraper.py`

```
main()                                # charge .env + configure logging ici (pas au module level)
  └─ get_session_cookie()             → login Selenium → cookie diedm_session
  └─ get_spaces()                     → HTTP API → liste des albums/années
  └─ process_space(driver, space, base_download_dir, session_cookie)
       └─ collect_article_data()      → DOM Selenium : (date, title, post_url) par article
       └─ process_post(article, ...)  → API JSON → toutes les photos d'un post
            └─ fetch_post_photos()    → GET /journal/{uuid}/posts/photos/{id}?per_page=100
            └─ download_image()       → HTTP GET de chaque `src` HD + file write
```

Selenium ne sert plus que pour le **login** et le **listing des articles**
(la page journal a besoin du DOM rendu pour récupérer les liens de posts).
Le téléchargement des photos est intégralement en `requests`.

### Key implementation details (TMA)

- **Auth**: `get_session_cookie()` → `login_with_credentials()` ouvre Chrome, remplit le formulaire en deux étapes (email → "Continuer" → password → "Je me connecte") et retourne le cookie `diedm_session`. Cookie injecté dans `requests` et le driver Selenium.
- **API photos**: `fetch_post_photos(space_uuid, post_id, cookie)` appelle l'endpoint paginé `/journal/{space}/posts/photos/{post}?page=N&per_page=100`. La réponse JSON expose `total`, `last_page`, `data: [...]` avec pour chaque photo un `src` HD direct (S3) et `extension`. **Pagination automatique** si > 100 photos, mais en pratique `per_page=100` couvre tous les posts observés.
- **URL HD**: les URLs `src` pointent vers `https://YEAR-{uuid}-gi.s3.toutemonannee.com/n1/{space}/hd/{file}.jpg?lastmod=...`. Le query string est strippé par `download_image()` avant la requête.
- **Naming**: dossier = `{YYYY-MM-DD ou date FR} - {titre}` ; fichier = `{NNN}_{YYYY-MM-DD}_{slug}.{ext}`. L'extension vient du champ `extension` du JSON (pas dérivée de l'URL).
- **EXIF date**: chaque image se voit attribuer `base_dt + index minutes` (10:00:00 + 1 min par photo, base = date du post parsée depuis le format FR).
- **Output path**: `DOWNLOAD_DIR` (obligatoire, lève `EnvironmentError`) ; lu dans `main()`, **pas** au niveau module (sinon `import school_photo_dl.tma` planterait sans `.env`).

### Flow dans `src/school_photo_dl/klassly/scraper.py`

```
main()                                # charge .env + configure logging ici
  └─ login()                          → Selenium remplit tel+password → klassroom_token
  └─ ImageFetcher(driver)             → construit la stratégie de DL à 3 niveaux
  └─ get_classes()                    → navigue /class, capture app.connect via CDP → classes
  └─ process_class(driver, fetcher, klass, download_dir)
       └─ collect_all_posts()         → boucle CDP klass.history jusqu'à épuisement
       └─ process_post(fetcher, ...)  → planifie tous les attachments du post
            └─ fetcher.fetch_many()   → batch parallèle (fetch JS) ou CDP unitaire
```

### Key implementation details (Klassly)

- **Auth**: formulaire en une étape (tel + password ensemble) → `button.kr-login-form__btn` ; cookie `klassroom_token` récupéré.
- **Classes**: extraites du champ `klasses` de `app.connect` capturé via CDP lors de la navigation `/class`.
- **Posts**: `klass.history` capturé via CDP pendant scroll ; dict keyed par postID avec `attachments` embarqués.
- **`ImageFetcher` — 3 niveaux de DL** (chaque niveau qui échoue est désactivé pour la session) :
  1. `requests` Python avec cookies + UA Chrome (rapide mais rejeté par anti-bot 403 sur klass.ly en pratique).
  2. **`fetch()` JS parallèle** injecté via `execute_async_script` : télécharge N URLs simultanément (concurrency=6) dans le contexte Chrome, encode en base64, renvoie via callback. Au premier 403 CORS (`Failed to fetch`), le driver est navigué une fois vers une URL `www.klass.ly` (`_warm_up_origin`) pour aligner l'origine et rendre les fetch suivants same-origin.
  3. Fallback CDP : navigation Chrome vers chaque URL + `Network.getResponseBody`.
- **URL normalization**: `data.klassroom.co/img/` → `www.klass.ly/_data/img/` (le second domaine est servi avec les bons CORS une fois warmé).
- **Batching par post**: `process_post` calcule d'abord tous les chemins de destination, filtre les fichiers déjà présents, puis fait **un seul `fetch_many`** pour les images manquantes. Plus de boucle séquentielle par image.
- **Output path**: `DOWNLOAD_DIR` (obligatoire) ; lu dans `main()`. `HEADLESS=false` pour mode visible.

### Shared

- `shared/driver.py` — `init_driver(headless=True, enable_cdp=False)` ; CDP requis pour Klassly.
- `shared/utils.py` — `configure_logging()` (INFO + horodatage), `safe_name()` (nettoie les caractères interdits dans les noms de fichier).

## Convention

- Logging Python `logging` au niveau INFO, stdout uniquement.
- Aucune lecture de variable d'env au niveau module — toujours dans `main()` — pour que `import school_photo_dl.*` reste sûr sans `.env`.
- Pas de `requirements.txt` : ajouter une dép = éditer `[project.dependencies]` dans `pyproject.toml`.
