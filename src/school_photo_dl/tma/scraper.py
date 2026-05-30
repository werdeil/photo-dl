"""Téléchargeur de photos depuis toutemonannee.com via Selenium."""

import os
import re
import time
import logging
from datetime import timedelta

from dotenv import load_dotenv
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
import requests

from school_photo_dl.shared.driver import init_driver
from school_photo_dl.shared.utils import (
    build_name_prefix,
    configure_logging,
    parse_french_date,
    safe_name,
    set_image_datetime,
    slugify,
)

logger = logging.getLogger(__name__)

BASE_TMA_URL = 'https://www.toutemonannee.com'
DASHBOARD_URL = f'{BASE_TMA_URL}/dashboard'


def login_with_credentials(driver, username, password):
    """Remplit le formulaire de login en 2 étapes et retourne le cookie diedm_session."""
    driver.get(f'{BASE_TMA_URL}/login')
    time.sleep(4)

    driver.find_element(By.NAME, 'username').send_keys(username)
    driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
    time.sleep(3)

    driver.find_element(By.NAME, 'password').send_keys(password)
    driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
    time.sleep(5)

    cookies = {c['name']: c['value'] for c in driver.get_cookies()}
    session_cookie = cookies.get('diedm_session')
    if not session_cookie or '/connect' in driver.current_url or '/login' in driver.current_url:
        raise ValueError("Login échoué : vérifiez TMA_USERNAME et TMA_PASSWORD.")

    logger.info("Connexion réussie, cookie de session récupéré.")
    return session_cookie


def get_session_cookie(driver):
    """Retourne le cookie diedm_session via login Selenium."""
    username = os.getenv('TMA_USERNAME')
    password = os.getenv('TMA_PASSWORD')
    if not username or not password:
        raise ValueError(
            "Définissez TMA_USERNAME et TMA_PASSWORD dans le .env."
        )
    return login_with_credentials(driver, username, password)



def get_spaces(session_cookie):
    """Récupère la liste des espaces/albums via l'API."""
    list_response = requests.get(
        f'{BASE_TMA_URL}/spaces/list',
        cookies={'diedm_session': session_cookie},
        timeout=10
    )
    data = list_response.json()
    spaces = []
    for space in data['spaces']:
        logger.info("UUID: %s, Année : %s, Nom : %s",
                    space['uuid'], space['display_years'], space['display_name'])
        spaces.append({
            'name': space['display_name'],
            'uuid': space['uuid'],
            'years': space.get('display_years', ''),
        })
    for space in data.get('spaces_soon_archived', []):
        logger.info("UUID: %s, Année : %s, Nom (archivé) : %s",
                    space['uuid'], space['display_years'], space['display_name'])
        spaces.append({
            'name': space['display_name'],
            'uuid': space['uuid'],
            'years': space.get('display_years', ''),
        })
    return spaces


def scroll_to_load_all_articles(driver):
    """Scrolle jusqu'en bas pour déclencher le chargement paresseux de tous les articles."""
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    articles = driver.find_elements(By.CSS_SELECTOR, "article:has(button.gallery-trigger)")
    prev_count = 0
    while len(articles) > prev_count:
        prev_count = len(articles)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        articles = driver.find_elements(By.CSS_SELECTOR, "article:has(button.gallery-trigger)")
        logger.debug("Articles après scroll : %d", len(articles))
    return articles


def collect_article_data(driver):
    """Collecte (date, title, post_url) de tous les articles sans naviguer hors de la page."""
    articles = scroll_to_load_all_articles(driver)
    logger.info("Nombre total d'articles : %d", len(articles))
    result = []
    for article in articles:
        try:
            date = (article.find_element(By.CSS_SELECTOR, "div.day").text + " "
                    + article.find_element(By.CSS_SELECTOR, "div.month").text)
        except NoSuchElementException:
            date = "unknown"
        try:
            link = article.find_element(By.XPATH, './/header//a[contains(@href,"/posts/")]')
            post_url = link.get_attribute('href')
            try:
                title_text = link.find_element(By.TAG_NAME, "span").text
            except NoSuchElementException:
                title_text = ""
        except NoSuchElementException:
            logger.warning("Article sans lien de post, ignoré.")
            continue
        result.append((date, title_text, post_url))
    return result


def download_image(hd_img_url, dest_path, session_cookie=None):
    """Télécharge une image HD vers dest_path. Retourne le chemin ou None."""
    img_name = os.path.basename(dest_path)
    if os.path.exists(dest_path):
        logger.debug("Déjà téléchargée : %s", img_name)
        return dest_path
    clean_img_url = re.sub(r'\?.*$', '', hd_img_url)
    try:
        cookies = {'diedm_session': session_cookie} if session_cookie else {}
        img_data = requests.get(clean_img_url, cookies=cookies, timeout=30).content
        with open(dest_path, 'wb') as img_file:
            img_file.write(img_data)
        logger.info("Image sauvegardée : %s", img_name)
        return dest_path
    except Exception as err:  # pylint: disable=broad-except
        logger.error("Erreur téléchargement %s : %s", clean_img_url, err)
        return None


def _build_image_filename(name_prefix, index, src_url):
    """Construit `NNN_{name_prefix}.ext`. Si name_prefix vide → `NNN.ext`."""
    clean = re.sub(r'\?.*$', '', src_url)
    ext = os.path.splitext(clean)[1].lower() or '.jpg'
    num = f"{index + 1:03d}"
    return f"{num}_{name_prefix}{ext}" if name_prefix else f"{num}{ext}"


def extract_image_urls_from_page(driver):
    """Cherche les URLs d'images (lightgallery, background-image, data-src)."""
    urls = set()

    for img in driver.find_elements(By.TAG_NAME, "img"):
        src = img.get_attribute('src') or ''
        if 'toutemonannee.com' in src and not any(
            x in src for x in ['logo', 'icon', 'avatar', 'navigation', 'reaction', 'asset']
        ):
            urls.add(src)
        data_src = img.get_attribute('data-src') or ''
        if 'toutemonannee.com' in data_src:
            urls.add(data_src)

    for element in driver.find_elements(By.XPATH, '//*[contains(@style,"url(")]'):
        style = element.get_attribute('style') or ''
        found = re.findall(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', style)
        for url in found:
            if 'toutemonannee.com' in url and not any(x in url for x in ['logo', 'icon', 'asset']):
                urls.add(url)

    for element in driver.find_elements(By.XPATH, '//*[@data-src]'):
        data_src = element.get_attribute('data-src') or ''
        if 'toutemonannee.com' in data_src:
            urls.add(data_src)

    return urls


def _apply_photo_date(img_path, base_dt, index):
    """Applique base_dt + index minutes à l'image si base_dt est défini."""
    if base_dt is None or img_path is None:
        return
    set_image_datetime(img_path, base_dt + timedelta(minutes=index))


def _handle_gallery_images(driver, article_folder_path, session_cookie,
                           base_dt=None, name_prefix=""):
    """Gère la pagination lightgallery et télécharge les images ; retourne le nombre téléchargé."""
    images = driver.find_elements(By.XPATH, '//*[contains(@id,"lg-container")]//img')
    if len(images) == 26:
        try:
            driver.find_element(By.XPATH, '//*[starts-with(@id,"lg-prev-")]').click()
            time.sleep(2)
            images = driver.find_elements(By.XPATH, '//*[contains(@id,"lg-container")]//img')
        except NoSuchElementException:
            pass
    if len(images) == 51:
        for _ in range(26):
            try:
                driver.find_element(By.XPATH, '//*[starts-with(@id,"lg-prev-")]').click()
                time.sleep(1)
            except NoSuchElementException:
                break
        time.sleep(2)
        images = driver.find_elements(By.XPATH, '//*[contains(@id,"lg-container")]//img')

    downloaded = 0
    for img in images:
        src = img.get_attribute('src') or ''
        if 'thumbs' in src:
            hd_url = src.replace('thumbs', 'hd')
            filename = _build_image_filename(name_prefix, downloaded, hd_url)
            dest_path = os.path.join(article_folder_path, filename)
            img_path = download_image(hd_url, dest_path, session_cookie)
            _apply_photo_date(img_path, base_dt, downloaded)
            downloaded += 1
    return downloaded


def _handle_fallback_images(driver, article_folder_path, session_cookie,
                            base_dt=None, name_prefix=""):
    """Extrait et télécharge les images directement depuis la page (fallback sans galerie)."""
    raw_urls = extract_image_urls_from_page(driver)
    hd_urls = {}
    for url in raw_urls:
        clean = re.sub(r'\?.*$', '', url)
        hd_clean = clean.replace('/thumbs/', '/hd/')
        hd_urls[os.path.basename(hd_clean)] = hd_clean

    downloaded = 0
    for hd_url in sorted(hd_urls.values()):
        filename = _build_image_filename(name_prefix, downloaded, hd_url)
        dest_path = os.path.join(article_folder_path, filename)
        img_path = download_image(hd_url, dest_path, session_cookie)
        _apply_photo_date(img_path, base_dt, downloaded)
        downloaded += 1
    return downloaded


def _build_post_naming(date, title_text, base_dt):
    """Retourne (folder_name, name_prefix) pour un post.

    Dossier : `YYYY-MM-DD - titre` si la date est parsable, sinon `date FR - titre`.
    Préfixe fichier : `YYYY-MM-DD_slug` avec dégradés propres si l'un manque.
    """
    iso_date = base_dt.strftime("%Y-%m-%d") if base_dt else ""
    folder_date = iso_date or date
    folder_label = f"{folder_date} - {title_text}" if title_text else folder_date
    folder_name = safe_name(folder_label)
    name_prefix = build_name_prefix(iso_date, slugify(title_text))
    return folder_name, name_prefix


def _try_open_gallery(driver):
    """Tente d'ouvrir la galerie lightgallery. Retourne True si des images sont visibles."""
    try:
        button = driver.find_element(By.CSS_SELECTOR, "button.gallery-trigger")
    except NoSuchElementException:
        return False
    driver.execute_script("arguments[0].click();", button)
    time.sleep(3)
    lg_imgs = driver.find_elements(By.XPATH, '//*[contains(@id,"lg-container")]//img')
    if not lg_imgs:
        return False
    logger.info("Galerie ouverte, %d images trouvées.", len(lg_imgs))
    return True


def _close_gallery(driver):
    """Ferme la galerie lightgallery si un bouton de fermeture est présent."""
    close_btns = driver.find_elements(By.CSS_SELECTOR, 'button.lg-close')
    if close_btns:
        close_btns[0].click()
        time.sleep(1)


def process_post(driver, article_data, save_folder_path, session_cookie=None, years_range=''):
    """Traite un article : ouvre la galerie et télécharge ses images."""
    date, title_text, post_url = article_data

    base_dt = parse_french_date(date, years_range)
    if base_dt is None:
        logger.debug("Date non parsable ('%s' + '%s'), EXIF inchangé.", date, years_range)

    folder_name, name_prefix = _build_post_naming(date, title_text, base_dt)
    article_folder_path = os.path.join(save_folder_path, folder_name)
    os.makedirs(article_folder_path, exist_ok=True)
    logger.info("Traitement du post : %s", title_text or post_url)

    driver.get(post_url)
    time.sleep(3)

    if _try_open_gallery(driver):
        downloaded = _handle_gallery_images(
            driver, article_folder_path, session_cookie, base_dt, name_prefix
        )
        logger.info("%d images téléchargées pour : %s", downloaded, title_text)
        _close_gallery(driver)
        return

    logger.info("Galerie non ouverte, extraction directe des images pour : %s", title_text)
    downloaded = _handle_fallback_images(
        driver, article_folder_path, session_cookie, base_dt, name_prefix
    )
    logger.info("%d images téléchargées pour : %s", downloaded, title_text)


def process_space(driver, space, base_download_dir, session_cookie=None):
    """Traite un espace/album : collecte les articles et les télécharge."""
    url = f"{BASE_TMA_URL}/journal/{space['uuid']}"
    logger.info("Traitement de l'espace : %s — %s", space['name'], url)
    save_folder_path = os.path.join(base_download_dir, space['name'])
    driver.add_cookie({'name': f'noShowAlbumPopupAnymore_{space["uuid"]}', 'value': '1'})
    driver.add_cookie({'name': 'noShowSouvenirPopupAnymore', 'value': '1'})
    driver.get(url)
    time.sleep(5)

    articles_data = collect_article_data(driver)
    years_range = space.get('years', '')

    for article_data in articles_data:
        process_post(driver, article_data, save_folder_path, session_cookie, years_range)


def main():
    """Point d'entrée principal : initialise le driver et traite tous les espaces."""
    load_dotenv()
    configure_logging()

    download_dir = os.getenv('DOWNLOAD_DIR')
    if not download_dir:
        raise EnvironmentError("DOWNLOAD_DIR is not set in .env")
    base_download_dir = os.path.expanduser(download_dir)

    headless = os.getenv('HEADLESS', 'true').lower() != 'false'
    driver = init_driver(headless=headless)
    try:
        driver.get(DASHBOARD_URL)
        session_cookie = get_session_cookie(driver)
        driver.add_cookie({'name': 'diedm_session', 'value': session_cookie})
        driver.get(DASHBOARD_URL)
        time.sleep(5)
        spaces = get_spaces(session_cookie)
        for space in spaces:
            process_space(driver, space, base_download_dir, session_cookie)
    finally:
        driver.quit()
    logger.info("Terminé. Images dans : %s", base_download_dir)


if __name__ == "__main__":
    main()
