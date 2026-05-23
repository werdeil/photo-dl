# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Python scraper that downloads photos from [toutemonannee.com](https://www.toutemonannee.com), a French photo/memory sharing platform. It uses Selenium to drive Chrome through JavaScript-heavy gallery pages and saves images locally organized by album and date.

## Setup

```bash
# Activate virtualenv (Python 3.13, already configured)
source .venv/bin/activate

# Required: valid session cookie from toutemonannee.com
export TMA_SESSION="<diedm_session cookie value>"
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

Downloads to `~/Documents/TMA/`, organized as `{space_name}/{date} - {title}/`.

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

- **Auth**: `get_session_cookie()` reads `TMA_SESSION` env var and injects it as the `diedm_session` cookie into both the `requests` session and the Selenium driver.
- **Image URL normalization**: thumbnail URLs containing `"thumbs"` are rewritten to their HD equivalents; query strings are stripped.
- **Carousel pagination**: articles can have >25 or >50 images; `process_article()` clicks "next page" controls and handles both cases.
- **Single-image articles**: handled as a special case separate from carousel logic.
- **Output path**: hardcoded to `~/Documents/TMA/`; `init_driver()` accepts a `headless` bool (defaults `False`).
- **Logging**: uses Python's `logging` at INFO level; no log file, stdout only.
