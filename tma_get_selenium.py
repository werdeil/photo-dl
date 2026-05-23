import os
import re
import time
import logging

from dotenv import load_dotenv
import requests

load_dotenv()
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DOWNLOAD_DIR = os.path.expanduser('~/Documents/TMA')
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

def get_session_cookie(driver=None):
    session = os.getenv('TMA_SESSION')
    if session:
        return session

    username = os.getenv('TMA_USERNAME')
    password = os.getenv('TMA_PASSWORD')
    if username and password:
        if driver is None:
            raise ValueError("Un driver Selenium est requis pour se connecter avec TMA_USERNAME/TMA_PASSWORD.")
        logger.info("TMA_SESSION absent, connexion avec TMA_USERNAME/TMA_PASSWORD...")
        return login_with_credentials(driver, username, password)

    raise ValueError(
        "Aucune authentification disponible. "
        "Définissez TMA_SESSION ou TMA_USERNAME+TMA_PASSWORD dans le .env."
    )

def init_driver(headless=True):
    logger.info("Initialisation du driver Chrome...")
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless=new')
        logger.info("Mode headless activé.")
    else:
        logger.warning("Mode headless désactivé, le navigateur s'ouvrira visuellement.")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_window_size(1920, 1080)
    return driver

def get_spaces(session_cookie):
    list_response = requests.get(
        f'{BASE_TMA_URL}/spaces/list',
        cookies={'diedm_session': session_cookie},
        timeout=10
    )
    data = list_response.json()
    spaces = []
    for space in data['spaces']:
        logger.info(f"UUID: {space['uuid']}, Année : {space['display_years']}, Nom : {space['display_name']}")
        spaces.append({'name': space['display_name'], 'uuid': space['uuid']})
    for space in data.get('spaces_soon_archived', []):
        logger.info(f"UUID: {space['uuid']}, Année : {space['display_years']}, Nom (archivé) : {space['display_name']}")
        spaces.append({'name': space['display_name'], 'uuid': space['uuid']})
    return spaces

def scroll_to_load_all_articles(driver):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    articles = driver.find_elements(By.CSS_SELECTOR, "article:has(button.gallery-trigger)")
    prev_count = 0
    while len(articles) > prev_count:
        prev_count = len(articles)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        articles = driver.find_elements(By.CSS_SELECTOR, "article:has(button.gallery-trigger)")
        logger.debug(f"Articles après scroll : {len(articles)}")
    return articles

def collect_article_data(driver):
    """Collecte (date, title, post_url) de tous les articles sans naviguer hors de la page."""
    articles = scroll_to_load_all_articles(driver)
    logger.info(f"Nombre total d'articles : {len(articles)}")
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

def download_image(hd_img_url, article_folder_path, session_cookie=None):
    clean_img_url = re.sub(r'\?.*$', '', hd_img_url)
    try:
        img_name = os.path.basename(clean_img_url)
        img_path = os.path.join(article_folder_path, img_name)
        if os.path.exists(img_path):
            logger.debug(f"Déjà téléchargée : {img_name}")
            return
        cookies = {'diedm_session': session_cookie} if session_cookie else {}
        img_data = requests.get(clean_img_url, cookies=cookies, timeout=30).content
        with open(img_path, 'wb') as f:
            f.write(img_data)
        logger.info(f"Image sauvegardée : {img_name}")
    except Exception as e:
        logger.error(f"Erreur téléchargement {clean_img_url} : {e}")

def extract_image_urls_from_page(driver):
    """Cherche les URLs d'images via plusieurs stratégies : lightgallery, background-image, data-src."""
    urls = set()

    # Stratégie 1 : img tags (lightgallery ou contenu direct)
    for img in driver.find_elements(By.TAG_NAME, "img"):
        src = img.get_attribute('src') or ''
        if 'toutemonannee.com' in src and not any(x in src for x in ['logo', 'icon', 'avatar', 'navigation', 'reaction', 'asset']):
            urls.add(src)
        data_src = img.get_attribute('data-src') or ''
        if 'toutemonannee.com' in data_src:
            urls.add(data_src)

    # Stratégie 2 : background-image dans les styles
    for el in driver.find_elements(By.XPATH, '//*[contains(@style,"url(")]'):
        style = el.get_attribute('style') or ''
        found = re.findall(r'url\(["\']?(https?://[^"\')\s]+)["\']?\)', style)
        for u in found:
            if 'toutemonannee.com' in u and not any(x in u for x in ['logo', 'icon', 'asset']):
                urls.add(u)

    # Stratégie 3 : data-src sur n'importe quel élément
    for el in driver.find_elements(By.XPATH, '//*[@data-src]'):
        data_src = el.get_attribute('data-src') or ''
        if 'toutemonannee.com' in data_src:
            urls.add(data_src)

    return urls

def process_post(driver, date, title_text, post_url, save_folder_path, session_cookie=None):
    folder_name = f"{date} - {title_text}" if title_text else date
    article_folder_path = os.path.join(save_folder_path, folder_name)
    os.makedirs(article_folder_path, exist_ok=True)
    logger.info(f"Traitement du post : {title_text or post_url}")

    driver.get(post_url)
    time.sleep(3)

    # Tenter d'ouvrir la galerie lightgallery
    gallery_opened = False
    try:
        button = driver.find_element(By.CSS_SELECTOR, "button.gallery-trigger")
        driver.execute_script("arguments[0].click();", button)
        time.sleep(3)
        lg_imgs = driver.find_elements(By.XPATH, '//*[contains(@id,"lg-container")]//img')
        if lg_imgs:
            gallery_opened = True
            logger.info(f"Galerie ouverte, {len(lg_imgs)} images trouvées.")
    except NoSuchElementException:
        pass

    if gallery_opened:
        # Pagination lightgallery si nécessaire
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
                download_image(hd_url, article_folder_path, session_cookie)
                downloaded += 1
        logger.info(f"{downloaded} images téléchargées pour : {title_text}")

        close_btns = driver.find_elements(By.CSS_SELECTOR, 'button.lg-close')
        if close_btns:
            close_btns[0].click()
            time.sleep(1)
        return

    # Fallback : chercher les images directement dans la page (background-image, data-src, img)
    logger.info(f"Galerie non ouverte, extraction directe des images pour : {title_text}")

    raw_urls = extract_image_urls_from_page(driver)
    # Convertir toutes les thumbs en hd, puis dédupliquer par nom de fichier
    hd_urls = {}
    for url in raw_urls:
        clean = re.sub(r'\?.*$', '', url)
        hd_clean = clean.replace('/thumbs/', '/hd/')
        filename = os.path.basename(hd_clean)
        hd_urls[filename] = hd_clean

    downloaded = 0
    for filename, hd_url in hd_urls.items():
        download_image(hd_url, article_folder_path, session_cookie)
        downloaded += 1
    logger.info(f"{downloaded} images téléchargées pour : {title_text}")

def process_space(driver, space, session_cookie=None):
    url = f"{BASE_TMA_URL}/journal/{space['uuid']}"
    logger.info(f"Traitement de l'espace : {space['name']} — {url}")
    save_folder_path = os.path.join(BASE_DOWNLOAD_DIR, space['name'])
    driver.add_cookie({'name': f'noShowAlbumPopupAnymore_{space["uuid"]}', 'value': '1'})
    driver.add_cookie({'name': 'noShowSouvenirPopupAnymore', 'value': '1'})
    driver.get(url)
    time.sleep(5)

    # Collecter toutes les données avant de naviguer ailleurs
    articles_data = collect_article_data(driver)

    for date, title_text, post_url in articles_data:
        process_post(driver, date, title_text, post_url, save_folder_path, session_cookie)

def main():
    driver = init_driver()
    try:
        driver.get(DASHBOARD_URL)
        session_cookie = get_session_cookie(driver)
        driver.add_cookie({'name': 'diedm_session', 'value': session_cookie})
        driver.get(DASHBOARD_URL)
        time.sleep(5)
        spaces = get_spaces(session_cookie)
        for space in spaces:
            process_space(driver, space, session_cookie)
    finally:
        driver.quit()
    logger.info(f"Terminé. Images dans : {BASE_DOWNLOAD_DIR}")

if __name__ == "__main__":
    main()
