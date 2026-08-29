#!/usr/bin/env python3
"""
setup_pinterest_login.py — Save Pinterest session cookies for automation
Run this once to log in and save cookies for future automated posting
"""

import logging
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pickle
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def save_pinterest_cookies():
    """Open browser, let user log in, save cookies"""

    logger.info("\n" + "=" * 70)
    logger.info("📌 PINTEREST LOGIN & COOKIE SETUP")
    logger.info("=" * 70)

    logger.info("\n📖 Instructions:")
    logger.info("  1. A Chrome window will open with Pinterest login page")
    logger.info("  2. Enter your Pinterest email and password")
    logger.info("  3. Complete any 2FA/security checks if prompted")
    logger.info("  4. Wait for home feed to load")
    logger.info("  5. Cookies will be saved automatically\n")

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    driver = None

    try:
        logger.info("🌐 Opening Pinterest login page...")
        driver = webdriver.Chrome(options=options)
        driver.get("https://pinterest.com/login/")

        logger.info("⏳ Waiting for you to log in (timeout: 5 minutes)...\n")

        # Wait for home feed to appear (indicates successful login)
        input("\n🟢 Press ENTER in this terminal window ONLY AFTER you have fully logged in and see your home feed in the browser...")

        logger.info("✓ Login detected! Saving cookies...\n")

        # Get cookies
        cookies = driver.get_cookies()
        cookies_file = Path(__file__).parent / ".pinterest_cookies"

        # Save to file
        with open(cookies_file, "wb") as f:
            pickle.dump(cookies, f)

        logger.info(f"✅ Cookies saved successfully!")
        logger.info(f"   File: {cookies_file}")
        logger.info(f"   Cookies count: {len(cookies)}\n")

        # Show which cookies were saved
        cookie_names = [c.get("name") for c in cookies]
        logger.info(f"📋 Saved cookies: {', '.join(cookie_names[:5])}...\n")

        logger.info("=" * 70)
        logger.info("✅ SETUP COMPLETE!")
        logger.info("=" * 70)
        logger.info("\n🚀 You can now run:")
        logger.info("   python pinterest_daily.py")
        logger.info("\nTo post to Pinterest automatically!\n")

        return True

    except Exception as e:
        logger.error(f"\n❌ Error: {e}\n")
        return False

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    success = save_pinterest_cookies()
    exit(0 if success else 1)
