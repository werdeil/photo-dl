# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Python scraper that downloads photos from [toutemonannee.com](https://www.toutemonannee.com), a French photo/memory sharing platform. It uses Selenium to drive Chrome through JavaScript-heavy gallery pages and saves images locally organized by album and date.

## Setup

```bash
# Activate virtualenv (Python 3.13, already configured)
source .venv/bin/activate
```

Auth via `.env` :

```bash
TMA_USERNAME="email@example.com"
TMA_PASSWORD="motdepasse"

# Dossier de téléchargement (obligatoire)
TMA_DOWNLOAD_DIR="/chemin/vers/dossier"
```

Install dependencies:

```bash
pip3 install -r requirements.txt
```

Key packages: `selenium==4.33.0`, `requests==2.32.3`, `webdriver-manager==4.0.2`, `beautifulsoup4==4.13.4`.

## Running

```bash
python3 tma_get_selenium.py
```

Downloads to `TMA_DOWNLOAD_DIR`, organized as `{space_name}/{date} - {title}/`.

## Architecture

### Flow in `tma_get_selenium.py`

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
