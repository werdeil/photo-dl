"""Téléchargeur de photos depuis fr.klass.ly via Selenium + CDP."""

import base64
import json
import os
import time
import logging
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

from school_photo_dl.shared.driver import init_driver
from school_photo_dl.shared.utils import (
    build_name_prefix,
    configure_logging,
    first_sentence,
    safe_name,
    set_image_datetime,
    slugify,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://fr.klass.ly"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(driver, username, password):
    """Remplit le formulaire klass.ly et retourne les cookies de session."""
    driver.get(BASE_URL)
    wait = WebDriverWait(driver, 20)

    # Formulaire en une étape : téléphone + mot de passe affichés ensemble
    phone_field = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[type='tel'], input[type='email'], input[name='email']")
    ))
    phone_field.send_keys(username)
    time.sleep(1)

    pwd_field = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[type='password']")
    ))
    pwd_field.send_keys(password)
    time.sleep(1)

    driver.find_element(By.CSS_SELECTOR, "button.kr-login-form__btn").click()
    time.sleep(6)

    cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
    if "klassroom_token" not in cookies:
        raise ValueError(
            "Login échoué : klassroom_token absent. "
            "Vérifiez KLASSLY_USERNAME / KLASSLY_PASSWORD dans .env."
        )
    logger.info("Connexion réussie.")
    return cookies


# ---------------------------------------------------------------------------
# CDP : helpers
# ---------------------------------------------------------------------------

def _flush_cdp_json(driver, url_fragment):
    """
    Consomme les logs CDP performance et retourne les corps JSON de toutes
    les réponses dont l'URL contient url_fragment, depuis le dernier appel.
    """
    logs = driver.get_log("performance")
    results = []
    for entry in logs:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") != "Network.responseReceived":
            continue
        url = msg["params"]["response"]["url"]
        if url_fragment not in url:
            continue
        req_id = msg["params"]["requestId"]
        try:
            raw = driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": req_id}
            )
            results.append(json.loads(raw.get("body", "{}")))
        except (WebDriverException, json.JSONDecodeError):
            pass
    return results


_CDP_LOAD_TIMEOUT = 10.0
_CDP_POLL_INTERVAL = 0.1


def _cdp_get_image_body(driver, url):
    """
    Navigue vers l'URL image avec le driver et retourne le contenu binaire
    via CDP. Le serveur www.klass.ly refuse souvent les requêtes Python mais
    accepte le browser Chrome : cette méthode contourne le blocage.

    Attend `Network.loadingFinished` sur le requestId de l'image (jusqu'à
    `_CDP_LOAD_TIMEOUT` secondes) au lieu d'un sleep fixe.
    """
    driver.get_log("performance")  # vide le buffer
    driver.get(url)

    target_req_id = None
    deadline = time.monotonic() + _CDP_LOAD_TIMEOUT
    while time.monotonic() < deadline:
        for entry in driver.get_log("performance"):
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method")
            params = msg.get("params", {})

            if method == "Network.responseReceived":
                resp = params.get("response", {})
                resp_url = resp.get("url", "")
                if (resp.get("status") == 200
                        and any(resp_url.lower().endswith(ext) for ext in IMG_EXTS)):
                    target_req_id = params.get("requestId")
            elif method == "Network.loadingFinished" and target_req_id:
                if params.get("requestId") == target_req_id:
                    try:
                        raw = driver.execute_cdp_cmd(
                            "Network.getResponseBody", {"requestId": target_req_id}
                        )
                    except (WebDriverException, json.JSONDecodeError):
                        return None
                    if raw.get("base64Encoded"):
                        return base64.b64decode(raw["body"])
                    return raw["body"].encode()

        time.sleep(_CDP_POLL_INTERVAL)

    return None


# ---------------------------------------------------------------------------
# Téléchargement multi-stratégies
# ---------------------------------------------------------------------------

_JS_PARALLEL_FETCH = r"""
const urls = arguments[0];
const concurrency = arguments[1];
const callback = arguments[arguments.length - 1];

async function fetchOne(url) {
  try {
    const r = await fetch(url, {credentials: 'include'});
    if (!r.ok) return {url, error: 'HTTP ' + r.status};
    const blob = await r.blob();
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const s = reader.result;
        const idx = s.indexOf(',');
        resolve({url, data: idx >= 0 ? s.slice(idx + 1) : s});
      };
      reader.onerror = () => resolve({url, error: 'reader-error'});
      reader.readAsDataURL(blob);
    });
  } catch (e) {
    return {url, error: String(e && e.message || e)};
  }
}

(async () => {
  const results = new Array(urls.length);
  let cursor = 0;
  async function worker() {
    while (cursor < urls.length) {
      const i = cursor++;
      results[i] = await fetchOne(urls[i]);
    }
  }
  const n = Math.min(concurrency, urls.length);
  await Promise.all(Array.from({length: n}, () => worker()));
  callback(results);
})();
"""


class ImageFetcher:
    """Stratégie de téléchargement à trois niveaux.

    1. `requests` Python (rapide mais souvent 403 sur klass.ly).
    2. `fetch()` JS injecté dans Chrome (parallèle, same-origin OK, contourne
       les blocages anti-bots Python).
    3. Fallback CDP par navigation Chrome (lent mais toujours fonctionnel).

    Chaque niveau qui échoue est désactivé pour le reste de la session.
    """

    def __init__(self, driver):
        self.driver = driver
        self.session = self._build_session(driver)
        self._requests_enabled = True
        self._js_enabled = True
        self._origin_warmed_up = False
        try:
            driver.set_script_timeout(120)
        except WebDriverException:
            pass

    @staticmethod
    def _build_session(driver):
        session = requests.Session()
        for cookie in driver.get_cookies():
            kwargs = {"name": cookie["name"], "value": cookie["value"]}
            if "domain" in cookie:
                kwargs["domain"] = cookie["domain"]
            if "path" in cookie:
                kwargs["path"] = cookie["path"]
            try:
                session.cookies.set(**kwargs)
            except (TypeError, ValueError):
                session.cookies.set(cookie["name"], cookie["value"])
        try:
            user_agent = driver.execute_script("return navigator.userAgent")
        except WebDriverException:
            user_agent = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        session.headers.update({
            "User-Agent": user_agent,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "same-site",
        })
        return session

    def _try_requests(self, url):
        if not self._requests_enabled:
            return None
        try:
            resp = self.session.get(url, timeout=30, allow_redirects=True)
        except requests.RequestException as exc:
            logger.warning(
                "requests indisponible (%s) ; bascule sur fetch JS / CDP.", exc,
            )
            self._requests_enabled = False
            return None
        if resp.status_code == 200 and resp.content:
            return resp.content
        logger.warning(
            "requests refusé (HTTP %s) ; bascule sur fetch JS / CDP.",
            resp.status_code,
        )
        self._requests_enabled = False
        return None

    def _run_js_fetch(self, urls, concurrency):
        try:
            return self.driver.execute_async_script(
                _JS_PARALLEL_FETCH, urls, concurrency,
            )
        except WebDriverException as exc:
            logger.warning(
                "execute_async_script échoué (%s) ; bascule en CDP.", exc,
            )
            self._js_enabled = False
            return None

    @staticmethod
    def _parse_js_results(raw, urls):
        out = {url: None for url in urls}
        errors = []
        for entry in raw or []:
            url = entry.get("url")
            if url not in out:
                continue
            if entry.get("data"):
                try:
                    out[url] = base64.b64decode(entry["data"])
                except (TypeError, ValueError):
                    pass
            elif entry.get("error") and len(errors) < 3:
                errors.append(entry["error"])
        return out, errors

    def _warm_up_origin(self, url):
        """Aligne le document du driver sur www.klass.ly pour rendre fetch JS
        same-origin. Coût : une navigation Chrome (~quelques centaines de ms).
        """
        try:
            self.driver.get(url)
        except WebDriverException as exc:
            logger.warning("warm-up origine échoué (%s).", exc)
            return False
        self._origin_warmed_up = True
        logger.info("Origine alignée sur www.klass.ly pour fetch JS same-origin.")
        return True

    def _try_js_batch(self, urls, concurrency):
        """Tente un fetch JS parallèle. Retourne dict[url -> bytes ou None]."""
        if not self._js_enabled or not urls:
            return {}

        raw = self._run_js_fetch(urls, concurrency)
        if raw is None:
            return {}
        out, errors = self._parse_js_results(raw, urls)
        any_ok = any(v is not None for v in out.values())

        # En cas d'échec total, retenter une fois après warm-up de l'origine
        # (cause probable : CORS fr.klass.ly → www.klass.ly).
        if not any_ok and not self._origin_warmed_up and self._warm_up_origin(urls[0]):
            raw = self._run_js_fetch(urls, concurrency)
            if raw is not None:
                out, errors = self._parse_js_results(raw, urls)
                any_ok = any(v is not None for v in out.values())

        if not any_ok:
            logger.warning(
                "fetch JS en page bloqué (échantillon : %s) ; bascule en CDP.",
                errors or "vide",
            )
            self._js_enabled = False
        return out

    def fetch_many(self, urls, concurrency=6):
        """Télécharge plusieurs URLs en parallèle si possible.

        Retourne dict[url -> bytes ou None].
        Ordre des stratégies : fetch JS parallèle (si actif) → CDP unitaire
        pour les URLs encore manquantes.
        """
        if not urls:
            return {}
        results = self._try_js_batch(urls, concurrency)
        for url in urls:
            if results.get(url) is None:
                # Fallback unitaire : requests (si encore actif) puis CDP.
                data = self._try_requests(url)
                if data is None:
                    data = _cdp_get_image_body(self.driver, url)
                results[url] = data
        return results

    def fetch(self, url):
        """Télécharge une seule URL ; raccourci utilisant `fetch_many`."""
        return self.fetch_many([url]).get(url)


# ---------------------------------------------------------------------------
# Classes  (via app.connect capturé lors de la navigation /class)
# ---------------------------------------------------------------------------

def get_classes(driver):
    """
    Navigue vers /class, capture la réponse app.connect et retourne la liste
    des classes sous la forme [{'id': ..., 'name': ..., 'url': ...}, ...].
    """
    driver.get_log("performance")  # vide les logs précédents
    driver.get(f"{BASE_URL}/class")
    time.sleep(5)

    for body in _flush_cdp_json(driver, "app.connect"):
        klasses = body.get("klasses", {})
        if not klasses:
            continue
        result = []
        for klass_id, klass in klasses.items():
            key = klass.get("key") or klass_id
            name = klass.get("natural_name") or key
            result.append({
                "id": klass_id,
                "name": name,
                "url": f"{BASE_URL}/class/inside/{key}",
            })
        logger.info("%d classe(s) trouvée(s).", len(result))
        return result

    logger.warning("Aucune classe trouvée dans app.connect.")
    return []


# ---------------------------------------------------------------------------
# Posts  (via klass.history capturé lors de la navigation vers la classe)
# ---------------------------------------------------------------------------

def collect_all_posts(driver):
    """
    Scrolle la page courante et accumule tous les posts retournés par
    klass.history (appel CDP destructif : vide les logs à chaque itération).
    """
    all_posts = {}
    prev_count = -1

    while True:
        for body in _flush_cdp_json(driver, "klass.history"):
            if body.get("ok") and isinstance(body.get("posts"), dict):
                all_posts.update(body["posts"])

        if len(all_posts) == prev_count:
            break
        prev_count = len(all_posts)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)

    return all_posts


# ---------------------------------------------------------------------------
# Nommage
# ---------------------------------------------------------------------------

def _post_naming(post_id, post):
    """Retourne (folder_name, name_prefix, base_dt) pour un post klassly.

    - Dossier : `YYYY-MM-DD - {texte tronqué}` (fallback `unknown` / `post_id` si manquant).
    - Préfixe fichier : `YYYY-MM-DD_slug` avec dégradés alignés sur TMA.
    """
    epoch_ms = post.get("date", 0)
    base_dt = None
    iso_date = ""
    if epoch_ms:
        base_dt = datetime.fromtimestamp(epoch_ms / 1000).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        iso_date = base_dt.strftime("%Y-%m-%d")

    raw_text = post.get("text") or post.get("title") or ""
    title = first_sentence(raw_text, max_len=60)
    folder_title = safe_name(title).strip("_").strip() if title else post_id
    folder_date = iso_date or "unknown"
    folder_name = f"{folder_date} - {folder_title}"

    name_prefix = build_name_prefix(iso_date, slugify(title))
    return folder_name, name_prefix, base_dt


# ---------------------------------------------------------------------------
# Téléchargement  (via Selenium/CDP car www.klass.ly bloque requests)
# ---------------------------------------------------------------------------

def _normalize_image_url(url):
    """
    Convertit les URLs data.klassroom.co/img/<UUID>.jpg
    vers www.klass.ly/_data/img/<UUID>.jpg (accessibles via Selenium).
    """
    return url.replace(
        "https://data.klassroom.co/img/",
        "https://www.klass.ly/_data/img/",
    )


def _attachment_filename(index, name_prefix, att):
    ext = (att.get("extension") or "jpg").lstrip(".").lower()
    num = f"{index + 1:03d}"
    return f"{num}_{name_prefix}.{ext}" if name_prefix else f"{num}.{ext}"


def _plan_post_downloads(post, post_id, class_dir):
    """Calcule la liste des téléchargements à effectuer pour un post.

    Retourne (folder, base_dt, items) avec items = liste de
    (index, url, dest, already_present).
    """
    attachments = post.get("attachments") or {}
    images = [a for a in attachments.values() if a.get("type") == "image"]
    if not images:
        return None, None, []

    folder_name, name_prefix, base_dt = _post_naming(post_id, post)
    folder = os.path.join(class_dir, folder_name)
    sorted_images = sorted(images, key=lambda a: a.get("position", 0))

    items = []
    for index, att in enumerate(sorted_images):
        url = _normalize_image_url(att.get("url", ""))
        if not url:
            continue
        dest = os.path.join(folder, _attachment_filename(index, name_prefix, att))
        items.append((index, url, dest, os.path.exists(dest)))
    return folder, base_dt, items


def process_post(fetcher, post_id, post, class_dir):
    """Télécharge toutes les images attachées à un post dans son dossier.

    Les images manquantes sont téléchargées en parallèle via `fetch_many`.
    """
    folder, base_dt, items = _plan_post_downloads(post, post_id, class_dir)
    if not items:
        return

    missing = [(i, url, dest) for (i, url, dest, exists) in items if not exists]
    if not missing:
        return

    os.makedirs(folder, exist_ok=True)
    urls = [m[1] for m in missing]
    fetched = fetcher.fetch_many(urls)

    for index, url, dest in missing:
        data = fetched.get(url)
        if data is None:
            logger.error("  Échec (aucun corps reçu) : %s", url)
            continue
        with open(dest, "wb") as out:
            out.write(data)
        logger.info("  Téléchargé : %s", os.path.basename(dest))
        if base_dt:
            set_image_datetime(dest, base_dt + timedelta(minutes=index))


def process_class(driver, fetcher, klass, download_dir):
    """Collecte tous les posts d'une classe et télécharge leurs images."""
    class_name = klass["name"]
    class_url = klass["url"]
    class_dir = os.path.join(download_dir, safe_name(class_name))
    logger.info("Classe : %s → %s", class_name, class_dir)

    driver.get_log("performance")  # vide les logs précédents
    driver.get(class_url)
    time.sleep(5)

    posts = collect_all_posts(driver)
    logger.info("  %d post(s) collectés.", len(posts))

    for post_id, post in posts.items():
        process_post(fetcher, post_id, post, class_dir)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main():
    """Point d'entrée : charge la config, authentifie et télécharge toutes les classes."""
    load_dotenv()
    configure_logging()

    download_dir = os.getenv("DOWNLOAD_DIR")
    if not download_dir:
        raise EnvironmentError("DOWNLOAD_DIR non défini dans .env")
    download_dir = os.path.expanduser(download_dir)

    username = os.getenv("KLASSLY_USERNAME")
    password = os.getenv("KLASSLY_PASSWORD")
    if not username or not password:
        raise EnvironmentError(
            "KLASSLY_USERNAME / KLASSLY_PASSWORD non définis dans .env"
        )

    headless = os.getenv("HEADLESS", "true").lower() != "false"
    driver = init_driver(headless=headless, enable_cdp=True)

    try:
        login(driver, username, password)
        fetcher = ImageFetcher(driver)

        classes = get_classes(driver)
        if not classes:
            logger.warning("Aucune classe trouvée.")
            return

        for klass in classes:
            process_class(driver, fetcher, klass, download_dir)
    finally:
        driver.quit()

    logger.info("Terminé. Images dans : %s", download_dir)


if __name__ == "__main__":
    main()
