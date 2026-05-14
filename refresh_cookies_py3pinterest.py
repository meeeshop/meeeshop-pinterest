#!/usr/bin/env python3
"""
Refresh Pinterest cookies by logging in directly with py3-pinterest
This creates fresh cookies without needing Chrome or browser-cookie3
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def load_credentials():
    """Load Pinterest credentials from .env"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    email = os.getenv("PINTEREST_EMAIL")
    password = os.getenv("PINTEREST_PASSWORD")
    username = os.getenv("PINTEREST_USERNAME")

    if not (email and password):
        logger.error("Missing PINTEREST_EMAIL or PINTEREST_PASSWORD in .env")
        return None

    return {
        "email": email,
        "password": password,
        "username": username or "meeeshop"
    }

def login_and_get_fresh_cookies():
    """Log in to Pinterest with py3-pinterest to get fresh cookies"""
    logger.info("=" * 70)
    logger.info("LOGGING INTO PINTEREST WITH PY3-PINTEREST")
    logger.info("=" * 70)

    creds = load_credentials()
    if not creds:
        return None

    try:
        from py3pin.Pinterest import Pinterest

        logger.info(f"Logging in as: {creds['email']}")
        logger.info(f"Username: {creds['username']}")

        # Create client - this will trigger login and create fresh cookies
        client = Pinterest(
            email=creds['email'],
            password=creds['password'],
            username=creds['username']
        )

        logger.info("✓ Pinterest client created")

        # Test the login by fetching boards
        logger.info("\nFetching boards to verify login...")
        boards = client.boards()

        if boards:
            logger.info(f"✓ Successfully logged in! Found {len(boards)} boards")
            return client
        else:
            logger.warning("Logged in but no boards returned")
            return client

    except Exception as e:
        logger.error(f"Login failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_cookies_from_client(client, username='meeeshop'):
    """Extract session cookies from py3-pinterest client"""
    try:
        # py3-pinterest stores session in the client object
        # The actual cookies are managed internally by the library

        # Try to access the session cookies
        if hasattr(client, '_session') and hasattr(client._session, 'cookies'):
            session_cookies = dict(client._session.cookies)
            logger.info(f"✓ Extracted {len(session_cookies)} cookies from session")

            pinterest_cookies = {}
            for name, value in session_cookies.items():
                if name in ('_pinterest_sess', 'csrftoken'):
                    pinterest_cookies[name] = value
                    logger.info(f"  - {name}: {str(value)[:30]}...")

            return pinterest_cookies if pinterest_cookies else session_cookies

        # Alternative: check if cookies stored in data directory
        data_dir = Path(__file__).parent / "data" / username
        if data_dir.exists():
            logger.info(f"Checking data directory: {data_dir}")
            for f in data_dir.glob("*"):
                logger.info(f"  Found: {f.name}")

        return None

    except Exception as e:
        logger.error(f"Failed to extract cookies: {e}")
        import traceback
        traceback.print_exc()
        return None

def save_cookies(cookies, creds):
    """Save cookies to py3-pinterest format and backup"""
    if not cookies:
        logger.error("No cookies to save")
        return False

    try:
        # Format 1: py3-pinterest cookies.json
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)

        user_dir = data_dir / creds['username']
        user_dir.mkdir(exist_ok=True)

        cookies_file = user_dir / "cookies.json"
        cookies_data = {
            "_pinterest_sess": cookies.get("_pinterest_sess"),
            "csrftoken": cookies.get("csrftoken"),
            "timestamp": datetime.now().isoformat(),
            "all_cookies": cookies
        }

        cookies_file.write_text(json.dumps(cookies_data, indent=2), encoding="utf-8")
        logger.info(f"✓ Saved to: {cookies_file}")

        # Format 2: Backup plain text
        backup_file = Path(__file__).parent / ".pinterest_cookies"
        backup_lines = [
            f"_pinterest_sess={cookies.get('_pinterest_sess', 'N/A')}",
            f"csrftoken={cookies.get('csrftoken', 'N/A')}",
            f"updated={datetime.now().isoformat()}",
            ""
        ]
        backup_file.write_text("\n".join(backup_lines), encoding="utf-8")
        logger.info(f"✓ Saved to: {backup_file}")

        return True

    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False

def main():
    logger.info("\n🔐 Refresh Pinterest Cookies via py3-pinterest Login\n")

    # Step 1: Log in
    client = login_and_get_fresh_cookies()
    if not client:
        logger.error("❌ Login failed")
        return False

    # Step 2: Load credentials for saving
    creds = load_credentials()

    # Step 3: Extract cookies from session
    cookies = extract_cookies_from_client(client, creds['username'])
    if not cookies:
        logger.warning("⚠ Could not extract cookies directly from client")
        logger.info("\nNote: py3-pinterest may store cookies automatically in data/<username>/")
        logger.info("Let's check what was created...")

        data_dir = Path(__file__).parent / "data" / creds['username']
        if data_dir.exists():
            logger.info(f"\nFiles in {data_dir}:")
            for f in data_dir.glob("*"):
                logger.info(f"  - {f.name} ({f.stat().st_size} bytes)")

        return True

    # Step 4: Save cookies
    if not save_cookies(cookies, creds):
        logger.error("❌ Failed to save cookies")
        return False

    logger.info("\n" + "=" * 70)
    logger.info("✅ COOKIES REFRESHED AND SAVED")
    logger.info("=" * 70)
    logger.info("\nNext: Run test_post_real_pins.py to post pins")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
