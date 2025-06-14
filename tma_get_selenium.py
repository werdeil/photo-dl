import os
import re
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

BASE_DOWNLOAD_DIR = os.path.expanduser('~/Documents/TMA')
BASE_TMA_URL = 'https://www.toutemonannee.com'
DASHBOARD_URL = f'{BASE_TMA_URL}/dashboard'

def get_session_cookie():
    session = os.getenv('TMA_SESSION')
    if not session:
        raise ValueError("La variable d'environnement 'TMA_SESSION' n'est pas définie.")
    return session

def init_driver():
    print("Initialisation du driver Chrome...")
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_window_size(1920, 1080)
    return driver

def get_spaces(session_cookie):
    list_response = requests.get(
        f'{BASE_TMA_URL}/spaces/list',
        cookies={'diedm_session': session_cookie},
        timeout=10
    )
    spaces = []
    for space in list_response.json()['spaces']:
        print(f"UUID: {space['uuid']}, Nom de l'espace : {space['display_name']}, Année : {space['display_years']}")
        spaces.append({'name': space['display_name'], 'uuid': space['uuid']})
    return spaces

def scroll_to_load_all_articles(driver):
    articles = driver.find_elements(By.CSS_SELECTOR, "article.reactor-post:has(button.gallery-trigger)")
    prev_count = 0
    while len(articles) > prev_count:
        prev_count = len(articles)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        articles = driver.find_elements(By.CSS_SELECTOR, "article.reactor-post:has(button.gallery-trigger)")
        print(f"Nombre d'articles trouvés après le scroll : {len(articles)}")
    return articles

def download_image(hd_img_url, article_folder_path):
    clean_img_url = re.sub(r'\?.*$', '', hd_img_url)
    try:
        img_data = requests.get(clean_img_url, timeout=10).content
        img_name = os.path.basename(clean_img_url)
        img_path = os.path.join(article_folder_path, img_name)
        with open(img_path, 'wb') as img_file:
            img_file.write(img_data)
        print(f"Image sauvegardée : {img_name}")
    except Exception as e:
        print(f"Erreur lors du téléchargement de l'image {clean_img_url} : {e}")

def process_article(driver, article, save_folder_path):
    h2 = article.find_element(By.CSS_SELECTOR, "h2.title")
    title_text = h2.text
    date = article.find_element(By.CSS_SELECTOR, "div.day").text + " " + article.find_element(By.CSS_SELECTOR, "div.month").text
    button = article.find_element(By.CSS_SELECTOR, "button.gallery-trigger")
    print("Processing gallery:", title_text)
    article_folder_path = os.path.join(save_folder_path, f"{date} - {title_text}")
    os.makedirs(article_folder_path, exist_ok=True)
    print(f"Les images seront sauvegardées dans : {article_folder_path}")

    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
        button.click()
        time.sleep(2)
        images = driver.find_elements(By.XPATH, '//*[@id="lg-container-1"]//img')
        if len(images) == 26:
            print("Carrousel avec 25 images, on va essayer de charger plus d'images...")
            try:
                back_button = driver.find_element(By.ID, 'lg-prev-1')
                back_button.click()
                print("Bouton précédent cliqué, on attend le chargement des images...")
                time.sleep(2)
            except Exception as e:
                print(f"Erreur lors du clic sur le bouton précédent : {e}")
            images = driver.find_elements(By.XPATH, '//*[@id="lg-container-1"]//img')
        print(f"Nombre d'images trouvées : {len(images)-1}")
        for img in images:
            img_url = img.get_attribute('src')
            if img_url and 'thumbs' in img_url:
                hd_img_url = img_url.replace('thumbs', 'hd')
                print(f"Téléchargement de l'image : {hd_img_url}")
                download_image(hd_img_url, article_folder_path)
        close_button = driver.find_elements(By.CSS_SELECTOR, 'button.lg-close')
        if close_button:
            close_button[0].click()
            time.sleep(1)
    except Exception as e:
        print(f"Erreur lors du traitement du bouton : {e}")

def process_space(driver, space, session_cookie):
    url = f"{BASE_TMA_URL}/journal/{space['uuid']}"
    print(f"\nTraitement de l'URL : {url}")
    url_id = os.path.basename(url)
    save_folder_path = os.path.join(BASE_DOWNLOAD_DIR, space['name'])
    driver.add_cookie({'name': f'noShowAlbumPopupAnymore_{url_id}', 'value': '1'})
    driver.get(url)
    time.sleep(5)
    articles = scroll_to_load_all_articles(driver)
    print("Recherche des articles contenant des galeries")
    for article in articles:
        process_article(driver, article, save_folder_path)

def main():
    session_cookie = get_session_cookie()
    driver = init_driver()
    try:
        driver.get(DASHBOARD_URL)
        print("Ajout des cookies de session...")
        driver.add_cookie({'name': 'diedm_session', 'value': session_cookie})
        driver.get(DASHBOARD_URL)
        time.sleep(5)
        spaces = get_spaces(session_cookie)
        for space in spaces:
            process_space(driver, space, session_cookie)
    finally:
        print("\nNettoyage et fermeture du navigateur.")
        driver.quit()
    print(f"Script terminé, toutes les images ont été téléchargées dans le dossier : {BASE_DOWNLOAD_DIR}")

if __name__ == "__main__":
    main()