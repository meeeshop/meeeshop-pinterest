#!/usr/bin/env python3
"""
refresh_pinterest_session.py — Interactive Pinterest Session & Cookie Refresher

Opens a visible Chromium browser window on your screen to log into Pinterest.
Once logged in, it automatically captures fresh session cookies, encodes them in base64,
updates secrets.enc with double-Fernet encryption, and outputs the base64 string for GitHub secrets.

Usage:
    python refresh_pinterest_session.py
"""

import os
import sys
import time
import json
import base64
import logging
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("SessionRefresher")

try:
    from secrets_manager import set_secret, get_secret, inject_to_env
    inject_to_env()
except Exception as e:
    logger.warning(f"Could not load secrets_manager: {e}")
    set_secret = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


def is_authenticated(context, current_url: str) -> bool:
    """Check if the browser context holds valid Pinterest auth cookies or is on an authenticated page."""
    cookies = context.cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies if "pinterest.com" in c.get("domain", "")}

    # Primary auth signals from Pinterest
    has_auth_flag = cookie_dict.get("_auth") == "1"
    has_session = bool(cookie_dict.get("_pinterest_sess"))

    # URL check: not on login or signup pages
    url_lower = current_url.lower()
    not_login_page = "login" not in url_lower and "signup" not in url_lower and "join" not in url_lower

    return (has_auth_flag or has_session) and not_login_page


def main():
    print("=" * 70)
    print("🔑 PINTEREST SESSION & COOKIE REFRESHER")
    print("=" * 70)
    print("\n🌐 A browser window will now open on your screen.")
    print("👉 Please log into your Pinterest account (MeeeShop) in that window.")
    print("   • Click 'Continue with Google' or log in with email/password.")
    print("   • As soon as you are logged in, this script will AUTOMATICALLY")
    print("     capture the session, encrypt it into secrets.enc, and close.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        context = browser.new_context(
            viewport=None,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        logger.info("Opening https://www.pinterest.com/login/ ...")
        page.goto("https://www.pinterest.com/login/", wait_until="domcontentloaded", timeout=45000)

        logger.info("⏳ Waiting for login... (Window will stay open for up to 30 minutes)")

        max_seconds = 1800
        start_time = time.time()
        authenticated = False

        while time.time() - start_time < max_seconds:
            try:
                current_url = page.url
                if is_authenticated(context, current_url):
                    # Give Pinterest an extra 3 seconds to finalize session cookies & CSRF tokens
                    time.sleep(3)
                    authenticated = True
                    break
            except Exception:
                pass

            time.sleep(2)

        if not authenticated:
            logger.error("❌ Timed out waiting for login (10 minutes elapsed). Browser closing.")
            browser.close()
            sys.exit(1)

        # Extract all cookies
        raw_cookies = context.cookies()
        pinterest_cookies = [
            c for c in raw_cookies if "pinterest.com" in c.get("domain", "")
        ]

        logger.info(f"✓ Detected successful login! Captured {len(pinterest_cookies)} Pinterest cookies.")
        browser.close()

    # Save to disk (.pinterest_cookies)
    cookies_file = ROOT / ".pinterest_cookies"
    with open(cookies_file, "w", encoding="utf-8") as f:
        json.dump(pinterest_cookies, f, indent=2)
    logger.info(f"✓ Saved raw cookies to {cookies_file.name}")

    # Encode to base64
    cookies_json = json.dumps(pinterest_cookies)
    cookies_b64 = base64.b64encode(cookies_json.encode("utf-8")).decode("utf-8")

    # Save to .pinterest_cookies_b64
    b64_file = ROOT / ".pinterest_cookies_b64"
    with open(b64_file, "w", encoding="utf-8") as f:
        f.write(cookies_b64)
    logger.info(f"✓ Saved base64 cookies to {b64_file.name}")

    # Update secrets.enc
    if set_secret:
        if set_secret("PINTEREST_COOKIES_B64", cookies_b64):
            logger.info("✓ Updated PINTEREST_COOKIES_B64 in secrets.enc")
        else:
            logger.warning("Could not update secrets.enc; base64 file is available.")

    print("\n" + "=" * 70)
    print("🎉 SUCCESS! PINTEREST SESSION REFRESH COMPLETE")
    print("=" * 70)
    print("1. Your local secrets.enc and .pinterest_cookies_b64 have been updated.")
    print("2. Commit and push secrets.enc to develop / 11.26 to fix GitHub Actions.")
    print("3. Optional: You can also update the GitHub Actions secret 'PINTEREST_COOKIES_B64'")
    print("   at: https://github.com/meeeshop/meeeshop-pinterest/settings/secrets/actions")
    print("=" * 70)
    print(f"\nPINTEREST_COOKIES_B64:\n{cookies_b64}\n")


if __name__ == "__main__":
    main()

