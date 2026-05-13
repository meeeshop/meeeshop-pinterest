#!/usr/bin/env python3
"""
extract_pinterest_cookies.py — Extract Pinterest cookies from Chrome profile
Since you're already logged in to Pinterest in Chrome, this extracts those cookies
"""

import sqlite3
import pickle
import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def extract_from_chrome_profile():
    """Extract cookies from Chrome profile"""
    try:
        profile_path = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default"

        if not profile_path.exists():
            print(f"✗ Chrome profile not found at: {profile_path}")
            return None

        print(f"✓ Found Chrome profile: {profile_path}")

        # Use Selenium with Chrome profile to get cookies
        options = webdriver.ChromeOptions()
        options.add_argument(f"user-data-dir={profile_path.parent}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")

        driver = webdriver.Chrome(options=options)

        try:
            print("📌 Opening Pinterest...")
            driver.get("https://pinterest.com")

            # Wait for page to load
            time.sleep(3)

            # Check if logged in by looking for home feed
            print("⏳ Checking if logged in...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='homefeed']"))
                )
                print("✓ Logged in detected!")
            except:
                print("⚠ Home feed not detected, but continuing to extract cookies...")

            # Get all cookies
            cookies = driver.get_cookies()

            if cookies:
                print(f"✓ Found {len(cookies)} cookies")

                # Save to file
                cookies_file = Path(__file__).parent / ".pinterest_cookies"
                with open(cookies_file, "wb") as f:
                    pickle.dump(cookies, f)

                print(f"✅ Cookies saved to: {cookies_file}")

                # Show some cookie names
                cookie_names = [c.get("name") for c in cookies[:5]]
                print(f"   Sample cookies: {cookie_names}")

                return cookies
            else:
                print("✗ No cookies found")
                return None

        finally:
            driver.quit()

    except Exception as e:
        print(f"✗ Error: {e}")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("🍪 EXTRACTING PINTEREST COOKIES FROM CHROME")
    print("=" * 60)
    print()

    cookies = extract_from_chrome_profile()

    print()
    print("=" * 60)
    if cookies:
        print("✅ COOKIES EXTRACTED SUCCESSFULLY")
    else:
        print("❌ FAILED TO EXTRACT COOKIES")
    print("=" * 60)
