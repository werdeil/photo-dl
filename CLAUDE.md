# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Python scrapers that download photos from two French school photo-sharing platforms:
- [toutemonannee.com](https://www.toutemonannee.com) — `tma/tma_get_selenium.py`
- [klass.ly](https://fr.klass.ly) — `klassly/klassly_get.py`

Both use Selenium to drive Chrome and save images locally organized by album/class and date.

## Setup

```bash
# Activate virtualenv (Python 3.13, already configured)
source .venv/bin/activate
```

Auth via `.env` :

```bash
TMA_USERNAME="email@example.com"
TMA_PASSWORD="motdepasse"
TMA_DOWNLOAD_DIR="/chemin/vers/dossier"

KLASSLY_USERNAME="+33600000000"
KLASSLY_PASSWORD="motdepasse"
KLASSLY_DOWNLOAD_DIR="/chemin/vers/dossier"
```

Install dependencies:

```bash
pip3 install -r requirements.txt
```

Key packages: `selenium==4.33.0`, `requests==2.32.3`, `webdriver-manager==4.0.2`, `beautifulsoup4==4.13.4`.

## Running

```bash
python3 tma/tma_get_selenium.py     # toutemonannee.com
python3 klassly/klassly_get.py      # klass.ly
```

TMA downloads to `TMA_DOWNLOAD_DIR`, organized as `{space_name}/{date} - {title}/`.
Klassly downloads to `KLASSLY_DOWNLOAD_DIR`, organized as `{class_name}/{date} - {post_text}/`.

## Architecture

### Flow in `tma/tma_get_selenium.py`

```
main()
  └─ get_spaces()          → HTTP API call to fetch all albums/years ("spaces")
  └─ process_space()       → per album: scroll to load all articles, then process each
       └─ scroll_to_load_all_articles()   → JS scroll loop to trigger lazy loading
       └─ process_article()              → extracts images from a gallery page
            └─ download_image()          → HTTP GET + file write
```

### Key implementation details

- **Auth**: `get_session_cookie()` appelle `login_with_credentials()` qui ouvre Chrome headless, remplit le formulaire en deux étapes (email → "Continuer" → password → "Je me connecte") et retourne le cookie `diedm_session`. Ce cookie est ensuite injecté dans la session `requests` et le driver Selenium.
- **Image URL normalization**: thumbnail URLs containing `"thumbs"` are rewritten to their HD equivalents; query strings are stripped.
- **Carousel pagination**: articles can have >25 or >50 images; `process_article()` clicks "next page" controls and handles both cases.
- **Single-image articles**: handled as a special case separate from carousel logic.
- **Output path**: défini par `TMA_DOWNLOAD_DIR` dans `.env` (obligatoire, lève `EnvironmentError` si absent); `init_driver()` accepts a `headless` bool (defaults `False`).
- **Logging**: uses Python's `logging` at INFO level; no log file, stdout only.

### Flow in `klassly/klassly_get.py`

```
main()
  └─ login()               → Selenium remplit tel+password, retourne klassroom_token cookie
  └─ get_classes()         → navigue /class, capture app.connect via CDP → liste des classes
  └─ process_class()       → par classe : scroll pour charger tous les posts
       └─ collect_all_posts()   → CDP klass.history en boucle jusqu'à épuisement
       └─ process_post()        → pour chaque post : télécharge les images
            └─ download_image() → Selenium navigue vers l'URL + capture CDP (requests bloqué par 403)
```

### Key implementation details (Klassly)

- **Auth**: formulaire en une étape (tel + password visibles ensemble) → `button.kr-login-form__btn`; cookie `klassroom_token` récupéré après login.
- **Classes**: extraites du champ `klasses` de la réponse `app.connect` capturée via CDP lors de la navigation `/class`.
- **Posts**: `klass.history` capturé via CDP pendant la navigation + scroll; posts retournés comme dict keyed by postID avec `attachments` embarqués.
- **Image download**: `www.klass.ly` et `data.klassroom.co` bloquent Python `requests` (403) mais acceptent Chrome → téléchargement via `driver.get(url)` + `Network.getResponseBody` CDP. URLs normalisées de `data.klassroom.co/img/` vers `www.klass.ly/_data/img/`.
- **Output path**: défini par `KLASSLY_DOWNLOAD_DIR` dans `.env`; `KLASSLY_HEADLESS=false` pour mode visible.
