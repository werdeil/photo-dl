from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import os
import re
import requests
import time

# Configuration
BASE_DOWNLOAD_DIR = os.path.expanduser('~/Documents/TMA')
BASE_TMA_URL = 'https://www.toutemonannee.com'
try:
    SESSION_COOKIE = os.getenv('TMA_SESSION')  # Assurez-vous de définir cette variable d'environnement
except KeyError:
    raise ValueError("La variable d'environnement 'TMA_SESSION' n'est pas définie.")

# Initialise le driver Selenium
print("Initialisation du driver Chrome...")
options = webdriver.ChromeOptions()
options.add_argument('headless')
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
driver.set_window_size(1920, 1080)

DASHBOARD_URL = f'{BASE_TMA_URL}/dashboard'

list_response = requests.get(f'{BASE_TMA_URL}/spaces/list', cookies={'diedm_session': SESSION_COOKIE})

spaces = []
for space in list_response.json()['spaces']:
    print(f"UUID: {space['uuid']}, Nom de l'espace : {space['display_name']}, Année : {space['display_years']}")
    spaces.append({'name': space['display_name'], 'uuid': space['uuid']})

try:

    driver.get(DASHBOARD_URL)
    print("Ajout des cookies de session...")
    driver.add_cookie({'name': 'diedm_session', 'value': SESSION_COOKIE})
    driver.get(DASHBOARD_URL)  # Recharge la page pour appliquer les cookies
    time.sleep(5)

    for space in spaces:
        url = f"{BASE_TMA_URL}/journal/{space['uuid']}"
        print(f"\nTraitement de l'URL : {url}")

        url_id = os.path.basename(url)
        save_folder_path = os.path.join(BASE_DOWNLOAD_DIR, space['name'])
        # os.makedirs(save_folder_path, exist_ok=True)

        print("Ajout du cookie qui enleve la popup...")
        driver.add_cookie({'name': f'noShowAlbumPopupAnymore_{url_id}', 'value': '1'})
        driver.get(url)

        # Attendre que la page soit complètement chargée
        time.sleep(5)

        # Trouver tous les articles contenant un bouton avec la classe 'gallery-trigger'
        articles = driver.find_elements(By.CSS_SELECTOR, "article.reactor-post:has(button.gallery-trigger)")

        # Parcourir chaque article et extraire le titre h2
        for article in articles:
            # Trouver le titre h2 dans l'article
            h2 = article.find_element(By.CSS_SELECTOR, "h2.title")
            title_text = h2.text

            # Trouver le bouton gallery-trigger dans l'article
            button = article.find_element(By.CSS_SELECTOR, "button.gallery-trigger")

            # Afficher le texte du titre et l'élément bouton
            print("Processing gallery:", title_text)
            article_folder_path = os.path.join(save_folder_path, title_text)
            os.makedirs(article_folder_path, exist_ok=True)
            print(f"Les images seront sauvegardées dans : {article_folder_path}")

            try:
                # Cliquer sur le bouton pour ouvrir le carrousel
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                button.click()
                time.sleep(2)  # Attendre que le carrousel s'ouvre

                # Trouver toutes les images dans le carrousel
                images = driver.find_elements(By.CSS_SELECTOR, 'img')

                for img in images:
                    img_url = img.get_attribute('src')
                    if img_url and 'thumbs' in img_url:
                        # Remplacer 'thumbs' par 'hd'
                        hd_img_url = img_url.replace('thumbs', 'hd')
                        print(f"Téléchargement de l'image : {hd_img_url}")
                        try:
                            # Nettoie l'URL pour enlever les paramètres de requête
                            clean_img_url = re.sub(r'\?.*$', '', hd_img_url)
                            img_data = requests.get(clean_img_url).content
                            img_name = os.path.basename(clean_img_url)
                            img_path = os.path.join(article_folder_path, img_name)
                            with open(img_path, 'wb') as img_file:
                                img_file.write(img_data)
                            print(f"Image sauvegardée : {img_name}")
                        except Exception as e:
                            print(f"Erreur lors du téléchargement de l'image {clean_img_url} : {e}")

                # Fermer le carrousel (si nécessaire, selon le site)
                close_button = driver.find_elements(By.CSS_SELECTOR, 'button.lg-close')
                if close_button:
                    close_button[0].click()
                    time.sleep(1)  # Attendre que le carrousel se ferme

            except Exception as e:
                print(f"Erreur lors du traitement du bouton : {e}")

finally:
    print("\nNettoyage et fermeture du navigateur.")
    driver.quit()

print("Script terminé.")
