"""Initialisation du driver Chrome partagée entre les scrapers."""

import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


def init_driver(headless=True, enable_cdp=False):
    """Initialise et retourne un driver Chrome.

    headless  : lance Chrome sans interface graphique
    enable_cdp: active la capture réseau CDP (requis pour Klassly)
    """
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
        logger.info("Mode headless activé.")
    else:
        logger.warning("Mode headless désactivé, le navigateur s'ouvrira visuellement.")
    if enable_cdp:
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )
    if enable_cdp:
        driver.execute_cdp_cmd("Network.enable", {})
    driver.set_window_size(1920, 1080)
    return driver
