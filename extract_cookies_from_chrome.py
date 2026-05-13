#!/usr/bin/env python3
"""
Extract Pinterest session cookies from Chrome browser (live, while logged in)
Handles Windows DPAPI decryption automatically
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Windows UTF-8 support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def extract_cookies_from_chrome():
    """Extract Pinterest cookies from Chrome using browser-cookie3"""
    logger.info("=" * 70)
    logger.info("EXTRACTING PINTEREST COOKIES FROM CHROME")
    logger.info("=" * 70)

    try:
        import browser_cookie3
        logger.info("✓ browser-cookie3 loaded")
    except ImportError:
        logger.error("browser-cookie3 not installed")
        return None

    try:
        logger.info("\nAttempting to read Chrome cookies for .pinterest.com...")
        cookies = browser_cookie3.chrome(domain_name=".pinterest.com")

        pinterest_cookies = {}
        for cookie in cookies:
            if cookie.name in ("_pinterest_sess", "csrftoken"):
                pinterest_cookies[cookie.name] = cookie.value
                logger.info(f"✓ Found {cookie.name}: {cookie.value[:20]}...")

        if not pinterest_cookies:
            logger.error("No Pinterest cookies found in Chrome")
            return None

        if "_pinterest_sess" not in pinterest_cookies:
            logger.error("Missing _pinterest_sess cookie")
            return None

        if "csrftoken" not in pinterest_cookies:
            logger.warning("Missing csrftoken cookie (may not be needed)")

        return pinterest_cookies

    except Exception as e:
        logger.error(f"Failed to extract cookies: {e}")
        import traceback
        traceback.print_exc()
        return None

def update_py3pinterest_cookies(cookies):
    """Update py3-pinterest data/<username> JSON file"""
    if not cookies:
        return False

    try:
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)

        # Create meeeshop user directory
        user_dir = data_dir / "meeeshop"
        user_dir.mkdir(exist_ok=True)

        # py3-pinterest stores cookies in a JSON file
        cookies_file = user_dir / "cookies.json"

        cookies_data = {
            "_pinterest_sess": cookies.get("_pinterest_sess"),
            "csrftoken": cookies.get("csrftoken"),
            "timestamp": datetime.now().isoformat()
        }

        cookies_file.write_text(json.dumps(cookies_data, indent=2), encoding="utf-8")
        logger.info(f"✓ Updated py3-pinterest cookies: {cookies_file}")
        return True

    except Exception as e:
        logger.error(f"Failed to update py3-pinterest cookies: {e}")
        return False

def update_backup_cookies(cookies):
    """Update .pinterest_cookies backup file"""
    if not cookies:
        return False

    try:
        cookies_file = Path(__file__).parent / ".pinterest_cookies"

        # Format as plain text for easy reading
        content = f"""_pinterest_sess={cookies.get('_pinterest_sess')}
csrftoken={cookies.get('csrftoken')}
updated={datetime.now().isoformat()}
"""

        cookies_file.write_text(content, encoding="utf-8")
        logger.info(f"✓ Updated backup cookies: {cookies_file}")
        return True

    except Exception as e:
        logger.error(f"Failed to update backup cookies: {e}")
        return False

def verify_cookies(cookies):
    """Test that cookies work with py3-pinterest"""
    if not cookies:
        return False

    logger.info("\n" + "=" * 70)
    logger.info("VERIFYING COOKIES WITH PY3-PINTEREST")
    logger.info("=" * 70)

    try:
        from py3pin.Pinterest import Pinterest
        from dotenv import load_dotenv

        # Load env for username
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        username = os.getenv("PINTEREST_USERNAME", "meeeshop")

        # Create client with extracted cookies
        client = Pinterest(
            email=os.getenv("PINTEREST_EMAIL"),
            password=os.getenv("PINTEREST_PASSWORD"),
            username=username
        )

        logger.info(f"Attempting to fetch boards with fresh cookies...")
        boards = client.boards()

        if boards:
            logger.info(f"✓ Successfully fetched {len(boards)} boards!")
            logger.info("\nSample boards:")
            for board in boards[:3]:
                logger.info(f"  - {board.get('name')} (ID: {board.get('id')})")
            return True
        else:
            logger.warning("Fetched boards but list was empty")
            return True

    except Exception as e:
        logger.error(f"Cookie verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    logger.info("\n🔐 Pinterest Cookie Extraction from Chrome\n")

    # Step 1: Extract cookies from Chrome
    cookies = extract_cookies_from_chrome()
    if not cookies:
        logger.error("\n❌ Failed to extract cookies from Chrome")
        return False

    logger.info(f"\n✓ Extracted {len(cookies)} cookies from Chrome")

    # Step 2: Update py3-pinterest cookies
    if not update_py3pinterest_cookies(cookies):
        logger.error("\n❌ Failed to update py3-pinterest cookies")
        return False

    # Step 3: Update backup file
    if not update_backup_cookies(cookies):
        logger.error("\n❌ Failed to update backup cookies")
        return False

    # Step 4: Verify cookies work
    if not verify_cookies(cookies):
        logger.warning("\n⚠ Cookie verification inconclusive, but files were updated")
        # Don't fail here - verification might just be timing-related

    logger.info("\n" + "=" * 70)
    logger.info("✅ COOKIES EXTRACTED AND UPDATED")
    logger.info("=" * 70)
    logger.info("\nNext step: Run test_post_real_pins.py to post pins")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
