#!/usr/bin/env python3
"""
list_all_links.py — List all links on Pinterest home page
"""

import time
import logging
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from credentials_manager import CredentialsManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

options = webdriver.ChromeOptions()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--start-maximized")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

try:
    if CredentialsManager.load_cookies(driver):
        logger.info("Going to Pinterest home...")
        driver.get("https://www.pinterest.com/")
        time.sleep(4)

        logger.info(f"Current URL: {driver.current_url}\n")

        # Get all links
        links = driver.find_elements("tag name", "a")
        logger.info(f"Found {len(links)} total links\n")

        logger.info("All links with href:\n")
        for i, link in enumerate(links):
            href = link.get_attribute("href") or ""
            aria = link.get_attribute("aria-label") or ""
            text = link.text or ""

            if href:
                logger.info(f"{i:2d}. href: {href}")
                if aria:
                    logger.info(f"    aria: {aria}")
                if text:
                    logger.info(f"    text: {text}\n")

finally:
    driver.quit()
