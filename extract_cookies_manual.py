#!/usr/bin/env python3
"""
Manual Pinterest cookie extraction for Chrome via Selenium WebDriver
Falls back to direct user input if browser is unavailable
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def extract_via_selenium():
    """Use Selenium to open Chrome and extract cookies programmatically"""
    logger.info("=" * 70)
    logger.info("EXTRACTING COOKIES VIA SELENIUM")
    logger.info("=" * 70)

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time

        logger.info("Starting Chrome with Selenium...")

        # Create Chrome options to avoid sandbox issues
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Try to connect to existing Chrome instance via debugger port
        options.add_argument("--remote-debugging-port=9222")

        driver = webdriver.Chrome(options=options)

        try:
            # Navigate to Pinterest
            logger.info("Navigating to Pinterest...")
            driver.get("https://www.pinterest.com/login/")

            # Wait for page to load
            time.sleep(3)

            # Check if already logged in
            try:
                driver.find_element(By.CLASS_NAME, "homefeed")
                logger.info("✓ Already logged into Pinterest")
            except:
                logger.warning("Not logged in - please log in manually in the browser")
                input("Press ENTER after you've logged in...")

            # Navigate to settings to access cookies
            driver.get("https://www.pinterest.com/settings/")
            time.sleep(2)

            # Extract cookies from WebDriver
            cookies = driver.get_cookies()
            pinterest_cookies = {}

            for cookie in cookies:
                if cookie['name'] in ('_pinterest_sess', 'csrftoken'):
                    pinterest_cookies[cookie['name']] = cookie['value']
                    logger.info(f"✓ Found {cookie['name']}")

            if not pinterest_cookies:
                logger.error("No Pinterest cookies found")
                return None

            return pinterest_cookies

        finally:
            driver.quit()
            logger.info("Chrome closed")

    except Exception as e:
        logger.error(f"Selenium extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def manual_input():
    """Prompt user to manually enter cookies from Chrome DevTools"""
    logger.info("=" * 70)
    logger.info("MANUAL COOKIE INPUT")
    logger.info("=" * 70)
    logger.info("\nTo get your cookies manually:")
    logger.info("1. Open Pinterest in Chrome and log in")
    logger.info("2. Press F12 to open DevTools")
    logger.info("3. Go to: Application → Cookies → https://www.pinterest.com")
    logger.info("4. Find '_pinterest_sess' and 'csrftoken' cookies")
    logger.info("5. Right-click → Copy value")
    logger.info("")

    cookies = {}

    sess = input("Enter _pinterest_sess cookie value: ").strip()
    if sess:
        cookies["_pinterest_sess"] = sess

    csrf = input("Enter csrftoken cookie value (optional): ").strip()
    if csrf:
        cookies["csrftoken"] = csrf

    if not cookies:
        logger.error("No cookies provided")
        return None

    logger.info(f"\n✓ Received {len(cookies)} cookies")
    return cookies

def update_cookie_files(cookies):
    """Update both py3-pinterest and backup cookie files"""
    if not cookies:
        return False

    try:
        # Update py3-pinterest format
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)

        user_dir = data_dir / "meeeshop"
        user_dir.mkdir(exist_ok=True)

        cookies_file = user_dir / "cookies.json"
        cookies_data = {
            "_pinterest_sess": cookies.get("_pinterest_sess"),
            "csrftoken": cookies.get("csrftoken"),
            "timestamp": datetime.now().isoformat()
        }
        cookies_file.write_text(json.dumps(cookies_data, indent=2), encoding="utf-8")
        logger.info(f"✓ Updated py3-pinterest cookies: {cookies_file}")

        # Update backup file
        backup_file = Path(__file__).parent / ".pinterest_cookies"
        backup_content = f"""_pinterest_sess={cookies.get('_pinterest_sess')}
csrftoken={cookies.get('csrftoken')}
updated={datetime.now().isoformat()}
"""
        backup_file.write_text(backup_content, encoding="utf-8")
        logger.info(f"✓ Updated backup cookies: {backup_file}")

        return True

    except Exception as e:
        logger.error(f"Failed to update cookie files: {e}")
        return False

def main():
    logger.info("\n🔐 Pinterest Cookie Extraction\n")

    # Try Selenium first
    cookies = extract_via_selenium()

    # Fall back to manual input
    if not cookies:
        logger.info("\n⚠ Selenium extraction failed, using manual input instead\n")
        cookies = manual_input()

    if not cookies:
        logger.error("❌ No cookies obtained")
        return False

    # Update files
    if not update_cookie_files(cookies):
        logger.error("❌ Failed to update cookie files")
        return False

    logger.info("\n" + "=" * 70)
    logger.info("✅ COOKIES EXTRACTED AND SAVED")
    logger.info("=" * 70)
    logger.info("\nNext: Run test_post_real_pins.py to post pins")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
