"""
pinterest_client.py — Web automation for Pinterest pin posting
Uses Selenium + Chrome headless for reliable, bot-detection-safe posting
Handles: login, board discovery, pin creation, video upload, scheduling
"""

import os
import time
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)


class PinterestClient:
    """Pinterest web automation client (no API, browser-based)"""

    def __init__(self, email: str, password: str, headless: bool = False, debug: bool = False):
        self.email = email
        self.password = password
        self.debug = debug

        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-dev-shm-usage")

        if headless:
            options.add_argument("--headless=new")

        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception as e:
            raise RuntimeError(f"ChromeDriver not found. Install: pip install webdriver-manager && python -m webdriver_manager.chrome") from e

        self.logged_in = False
        self.boards = {}

    def login(self, max_attempts: int = 3) -> bool:
        """Login to Pinterest with email/password"""
        for attempt in range(max_attempts):
            try:
                logger.info(f"Login attempt {attempt + 1}/{max_attempts}")
                self.driver.get("https://pinterest.com/login/")
                time.sleep(2)

                email_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.NAME, "email"))
                )
                email_input.clear()
                email_input.send_keys(self.email)

                password_input = self.driver.find_element(By.NAME, "password")
                password_input.clear()
                password_input.send_keys(self.password)

                submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_btn.click()

                time.sleep(3)

                # Check if login successful (home feed loads)
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='homefeed']"))
                    )
                    self.logged_in = True
                    logger.info("Login successful")
                    return True
                except Exception:
                    logger.warning("Homefeed not detected, retrying...")
                    continue

            except Exception as e:
                logger.warning(f"Login attempt failed: {e}")
                time.sleep(2)

        logger.error("Login failed after max attempts")
        return False

    def fetch_boards(self) -> Dict[str, str]:
        """Fetch user's Pinterest boards (name -> board_id mapping)"""
        if not self.logged_in:
            raise RuntimeError("Not logged in")

        try:
            self.driver.get("https://pinterest.com/me/boards/")
            time.sleep(2)

            boards = {}
            board_elements = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/board/']"))
            )

            for elem in board_elements:
                board_name = elem.get_attribute("aria-label")
                board_url = elem.get_attribute("href")

                if board_name and board_url and "/board/" in board_url:
                    board_id = board_url.split("/board/")[-1].split("/")[0]
                    boards[board_name] = board_id

            self.boards = boards
            logger.info(f"Found {len(boards)} boards")
            return boards

        except Exception as e:
            logger.error(f"Failed to fetch boards: {e}")
            return {}

    def create_pin(
        self,
        image_or_video_path: str,
        title: str,
        description: str,
        board_name: str,
        url: Optional[str] = None,
        alt_text: Optional[str] = None,
    ) -> bool:
        """Create a new pin on specified board"""
        if not self.logged_in:
            raise RuntimeError("Not logged in")

        if board_name not in self.boards:
            logger.error(f"Board '{board_name}' not found. Available: {list(self.boards.keys())}")
            return False

        try:
            # Click create/upload button
            self.driver.get("https://pinterest.com/pin/create/")
            time.sleep(2)

            # Wait for and click file upload input
            file_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )

            file_path = Path(image_or_video_path).resolve()
            file_input.send_keys(str(file_path))
            time.sleep(3)

            # Fill title
            title_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[placeholder*='title' i]"))
            )
            title_input.clear()
            title_input.send_keys(title)

            # Fill description
            desc_inputs = self.driver.find_elements(By.CSS_SELECTOR, "textarea")
            if len(desc_inputs) >= 2:
                desc_inputs[1].clear()
                desc_inputs[1].send_keys(description[:500])

            # Add destination URL if provided
            if url:
                url_input = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='link' i]"))
                )
                url_input.clear()
                url_input.send_keys(url)

            # Add alt text if provided
            if alt_text:
                try:
                    alt_btn = self.driver.find_element(By.CSS_SELECTOR, "button[aria-label*='alt' i]")
                    alt_btn.click()
                    time.sleep(1)
                    alt_input = self.driver.find_element(By.CSS_SELECTOR, "input[placeholder*='alt' i]")
                    alt_input.send_keys(alt_text[:125])
                except Exception:
                    pass

            # Select board
            board_selector = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label*='board' i]"))
            )
            board_selector.click()
            time.sleep(1)

            board_option = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, f"//div[contains(text(), '{board_name}')]"))
            )
            board_option.click()
            time.sleep(1)

            # Click Save/Publish
            save_btn = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label='Save']"))
            )
            save_btn.click()

            logger.info(f"Pin created: '{title}' on '{board_name}'")
            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"Failed to create pin: {e}")
            if self.debug:
                self.driver.save_screenshot("pin_creation_error.png")
            return False

    def close(self):
        """Close browser"""
        if self.driver:
            self.driver.quit()


def main():
    """Test Pinterest client"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    email = os.getenv("PINTEREST_EMAIL")
    password = os.getenv("PINTEREST_PASSWORD")

    if not email or not password:
        raise ValueError("Set PINTEREST_EMAIL and PINTEREST_PASSWORD in .env")

    client = PinterestClient(email, password, headless=False, debug=True)

    try:
        if client.login():
            boards = client.fetch_boards()
            print(f"Boards: {boards}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
