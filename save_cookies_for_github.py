#!/usr/bin/env python3
"""
save_cookies_for_github.py — Extract Pinterest session cookies for GitHub Actions secret.

Usage:
  1. Run this script to open Pinterest login in your browser
  2. Log in with your Pinterest account
  3. Cookies will be extracted and base64-encoded
  4. Copy the base64 string and create a GitHub secret: PINTEREST_COOKIES_B64
  5. Add the secret to GitHub Actions, then workflow will use it for authentication

This is the most reliable way to authenticate Pinterest in GitHub Actions CI/CD.
"""

import os
import json
import pickle
import base64
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, List

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def get_cookies_from_browser() -> Optional[Dict]:
    """
    Open browser, let user log in, extract cookies from Pinterest.

    Returns:
        Dict of cookies as {cookie_name: cookie_value} or None if failed
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time
    except ImportError:
        logger.error("Selenium not installed. Install with: pip install selenium")
        return None

    logger.info("\n" + "=" * 70)
    logger.info("📌 PINTEREST LOGIN FOR GITHUB ACTIONS SETUP")
    logger.info("=" * 70)
    logger.info("\n📖 Instructions:")
    logger.info("  1. A Chrome window will open with Pinterest login page")
    logger.info("  2. Enter your Pinterest email and password")
    logger.info("  3. Complete any 2FA/security checks if prompted")
    logger.info("  4. Wait for home feed to load")
    logger.info("  5. Cookies will be extracted and saved\n")

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
        WebDriverWait(driver, 300).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='homefeed']"))
        )

        logger.info("✓ Login detected! Extracting cookies...\n")

        # Get all cookies
        cookies_list = driver.get_cookies()

        # Convert to dict: {name: value}
        cookies_dict = {}
        for cookie in cookies_list:
            name = cookie.get('name')
            value = cookie.get('value')
            if name and value:
                cookies_dict[name] = value

        logger.info(f"✅ Extracted {len(cookies_dict)} cookies:")
        for name in list(cookies_dict.keys())[:5]:
            logger.info(f"   - {name}")
        if len(cookies_dict) > 5:
            logger.info(f"   ... and {len(cookies_dict) - 5} more")

        return cookies_dict

    except Exception as e:
        logger.error(f"\n❌ Error: {e}\n")
        return None

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def save_cookies_to_file(cookies_dict: Dict, output_file: Path) -> bool:
    """Save cookies as JSON file."""
    try:
        output_file.write_text(json.dumps(cookies_dict, indent=2), encoding='utf-8')
        logger.info(f"✓ Cookies saved to: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False


def encode_cookies_for_github(cookies_dict: Dict) -> str:
    """
    Encode cookies as base64 for GitHub secret.

    Returns:
        base64-encoded JSON string
    """
    cookies_json = json.dumps(cookies_dict)
    cookies_b64 = base64.b64encode(cookies_json.encode('utf-8')).decode('utf-8')
    return cookies_b64


def main():
    """Main workflow: login → extract cookies → encode for GitHub."""

    # Step 1: Get cookies from browser
    cookies_dict = get_cookies_from_browser()
    if not cookies_dict:
        logger.error("\n❌ Failed to extract cookies from browser")
        return False

    # Step 2: Save cookies to local file (for testing)
    cookies_file = Path(__file__).parent / ".pinterest_cookies_b64"
    if not save_cookies_to_file(cookies_dict, cookies_file):
        return False

    # Step 3: Encode for GitHub secret
    logger.info("\n" + "=" * 70)
    logger.info("🔐 GITHUB ACTIONS SECRET")
    logger.info("=" * 70 + "\n")

    cookies_b64 = encode_cookies_for_github(cookies_dict)

    logger.info("📋 Copy this value and create a GitHub secret:\n")
    logger.info("Secret name:  PINTEREST_COOKIES_B64")
    logger.info("Secret value:\n")
    logger.info(cookies_b64 + "\n")

    logger.info("=" * 70)
    logger.info("📌 NEXT STEPS:")
    logger.info("=" * 70)
    logger.info("\n1. Go to GitHub: https://github.com/YOUR_REPO/settings/secrets/actions")
    logger.info("2. Click 'New repository secret'")
    logger.info("3. Name: PINTEREST_COOKIES_B64")
    logger.info("4. Value: (paste the long string above)")
    logger.info("5. Click 'Add secret'")
    logger.info("\n6. Your GitHub Actions workflow will now authenticate with Pinterest! 🎉\n")

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
