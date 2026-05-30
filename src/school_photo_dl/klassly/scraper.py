"""Téléchargeur de photos depuis fr.klass.ly via Selenium + CDP."""

import base64
import json
import os
import time
import logging
from datetime import datetime

from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

from school_photo_dl.shared.driver import init_driver
from school_photo_dl.shared.utils import configure_logging, safe_name

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


def _cdp_get_image_body(driver, url):
    """
    Navigue vers l'URL image avec le driver et retourne le contenu binaire
    via CDP. Le serveur www.klass.ly refuse les requêtes Python mais accepte
    le browser Chrome : cette méthode contourne le blocage.
    """
    driver.get_log("performance")  # vide le buffer
    driver.get(url)
    time.sleep(2)

    logs = driver.get_log("performance")
    for entry in logs:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") != "Network.responseReceived":
            continue
        resp = msg["params"]["response"]
        if resp.get("status") != 200:
            continue
        resp_url = resp.get("url", "")
        if not any(resp_url.lower().endswith(ext) for ext in IMG_EXTS):
            continue
        req_id = msg["params"]["requestId"]
        try:
            raw = driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": req_id}
            )
            if raw.get("base64Encoded"):
                return base64.b64decode(raw["body"])
            return raw["body"].encode()
        except (WebDriverException, json.JSONDecodeError):
            pass
    return None


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

def post_folder_name(post_id, post):
    """Retourne le nom de dossier `YYYY-MM-DD - titre` pour un post."""
    epoch_ms = post.get("date", 0)
    date_str = (
        datetime.fromtimestamp(epoch_ms / 1000).strftime("%Y-%m-%d") if epoch_ms else "unknown"
    )
    text = post.get("text") or post.get("title") or ""
    if text:
        title = safe_name(text[:60]).strip("_").strip()
    else:
        title = post_id
    return f"{date_str} - {title}"


# ---------------------------------------------------------------------------
# Téléchargement  (via Selenium/CDP car www.klass.ly bloque requests)
# ---------------------------------------------------------------------------

def download_image(driver, url, dest_path):
    """
    Télécharge une image via Selenium+CDP.
    www.klass.ly et data.klassroom.co refusent les requêtes Python (403)
    mais acceptent le browser Chrome : on navigue vers l'URL et on capture
    le corps de réponse via CDP.
    """
    if os.path.exists(dest_path):
        logger.debug("Déjà téléchargé : %s", os.path.basename(dest_path))
        return False

    data = _cdp_get_image_body(driver, url)
    if data is None:
        logger.error("  Échec (aucun corps reçu) : %s", url)
        return False

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as out:
        out.write(data)
    logger.info("  Téléchargé : %s", os.path.basename(dest_path))
    return True


def _normalize_image_url(url):
    """
    Convertit les URLs data.klassroom.co/img/<UUID>.jpg
    vers www.klass.ly/_data/img/<UUID>.jpg (accessibles via Selenium).
    """
    return url.replace(
        "https://data.klassroom.co/img/",
        "https://www.klass.ly/_data/img/",
    )


def process_post(driver, post_id, post, class_dir):
    """Télécharge toutes les images attachées à un post dans son dossier."""
    attachments = post.get("attachments") or {}
    images = [a for a in attachments.values() if a.get("type") == "image"]
    if not images:
        return

    folder = os.path.join(class_dir, post_folder_name(post_id, post))
    os.makedirs(folder, exist_ok=True)

    for att in sorted(images, key=lambda a: a.get("position", 0)):
        url = _normalize_image_url(att.get("url", ""))
        if not url:
            continue
        ext = att.get("extension", "jpg")
        pos = att.get("position", 0)
        name = safe_name(att.get("name", f"{pos:03d}_{att.get('id', '')}"))
        if not name.lower().endswith(f".{ext}"):
            name = f"{pos:03d}_{name}"
        dest = os.path.join(folder, name)
        download_image(driver, url, dest)


def process_class(driver, klass, download_dir):
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
        process_post(driver, post_id, post, class_dir)


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

        classes = get_classes(driver)
        if not classes:
            logger.warning("Aucune classe trouvée.")
            return

        for klass in classes:
            process_class(driver, klass, download_dir)
    finally:
        driver.quit()

    logger.info("Terminé. Images dans : %s", download_dir)


if __name__ == "__main__":
    main()
