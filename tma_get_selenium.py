from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import os
import re
import requests
import time

# Configuration
TARGET_URLS = [
    'https://www.toutemonannee.com/journal/REDACTED_UUID_1',
    'https://www.toutemonannee.com/journal/REDACTED_UUID_2'
]
BASE_DOWNLOAD_DIR = os.path.expanduser('~/Documents/TMA')
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

DASHBOARD_URL = 'https://www.toutemonannee.com/dashboard'



try:

    driver.get(DASHBOARD_URL)
    print("Ajout des cookies de session...")
    driver.add_cookie({'name': 'diedm_session', 'value': SESSION_COOKIE})
    driver.get(DASHBOARD_URL)  # Recharge la page pour appliquer les cookies
    time.sleep(5)

    for url in TARGET_URLS:
        print(f"\nTraitement de l'URL : {url}")

        url_id = os.path.basename(url)
        url_dir = os.path.join(BASE_DOWNLOAD_DIR, url_id)
        os.makedirs(url_dir, exist_ok=True)
        print(f"Les images seront sauvegardées dans : {url_dir}")

        print("Ajout du cookie qui enleve la popup...")
        driver.add_cookie({'name': f'noShowAlbumPopupAnymore_{url_id}', 'value': '1'})
        driver.get(url)

        # Attendre que la page soit complètement chargée
        time.sleep(5)

        # Trouver tous les boutons "gallery-trigger"
        gallery_buttons = driver.find_elements(By.CSS_SELECTOR, 'button.gallery-trigger')

        for button in gallery_buttons:
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
                            img_path = os.path.join(url_dir, img_name)
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
