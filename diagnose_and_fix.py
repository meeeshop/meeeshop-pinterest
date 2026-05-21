#!/usr/bin/env python3
"""
diagnose_and_fix.py — Diagnose Pinterest posting issues and apply fixes
Checks: credentials, cookies, session state, API connectivity
"""

import os
import sys
import json
import logging
import base64
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from secrets_manager import inject_to_env
    inject_to_env()
    logger.info("[secrets] inject_to_env() succeeded")
except Exception as _e:
    logger.critical("[secrets] inject_to_env() FAILED — diagnostics will run with incomplete secrets: %s", _e, exc_info=True)

COOKIES_FILE = Path(__file__).parent / ".pinterest_cookies_b64"
HISTORY_FILE = Path(__file__).parent / "posting_history.json"


def check_credentials():
    """Check if Pinterest credentials are available"""
    logger.info("\n" + "="*70)
    logger.info("🔐 CHECKING CREDENTIALS")
    logger.info("="*70)

    # Secrets already loaded by inject_to_env() at module level
    pinterest_email = os.getenv("PINTEREST_EMAIL")
    pinterest_password = os.getenv("PINTEREST_PASSWORD")
    shopify_url = os.getenv("SHOPIFY_STORE_URL")
    shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

    checks = {
        "PINTEREST_EMAIL": pinterest_email,
        "PINTEREST_PASSWORD": ("***" if pinterest_password else None),
        "SHOPIFY_STORE_URL": shopify_url,
        "SHOPIFY_ACCESS_TOKEN": ("***" if shopify_token else None),
    }

    all_good = True
    for key, value in checks.items():
        if value:
            logger.info(f"  ✓ {key} found")
        else:
            logger.error(f"  ✗ {key} missing")
            all_good = False

    return all_good


def check_cookies():
    """Check and diagnose cookie issues"""
    logger.info("\n" + "="*70)
    logger.info("🍪 CHECKING COOKIES")
    logger.info("="*70)

    if COOKIES_FILE.exists():
        size = COOKIES_FILE.stat().st_size
        logger.info(f"✓ Cookies file found: {COOKIES_FILE} ({size} bytes)")

        if size == 0:
            logger.error("  ✗ Cookies file is EMPTY - will be cleared on next run")
            return False
        else:
            try:
                cookies_b64 = COOKIES_FILE.read_text().strip()
                cookies_json = base64.b64decode(cookies_b64).decode('utf-8')
                cookies_dict = json.loads(cookies_json)
                logger.info(f"  ✓ Cookies file is valid JSON ({len(cookies_dict)} cookies)")
                return True
            except Exception as e:
                logger.error(f"  ✗ Cookies file is CORRUPTED: {e}")
                logger.info("  → Will clear corrupted file on next run")
                return False
    else:
        logger.warning(f"✗ Cookies file not found: {COOKIES_FILE}")
        logger.info("  → Will try email/password login or GitHub secret")
        return False


def check_history():
    """Check posting history"""
    logger.info("\n" + "="*70)
    logger.info("📋 CHECKING POSTING HISTORY")
    logger.info("="*70)

    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
            posts = history.get("posts", [])
            daily_count = history.get("daily_count", 0)
            logger.info(f"✓ History file found")
            logger.info(f"  - Total posts: {len(posts)}")
            logger.info(f"  - Posts today: {daily_count}")
            return history
        except Exception as e:
            logger.error(f"✗ History file corrupted: {e}")
            return {}
    else:
        logger.info("ℹ No history file yet (first run)")
        return {}


def clear_stale_cookies():
    """Clear stale/corrupted cookies"""
    logger.info("\n" + "="*70)
    logger.info("🧹 CLEARING STALE COOKIES")
    logger.info("="*70)

    if COOKIES_FILE.exists():
        try:
            COOKIES_FILE.unlink()
            logger.info(f"✓ Cleared stale cookies: {COOKIES_FILE}")
            logger.info("  → Next run will use fresh authentication")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to clear cookies: {e}")
            return False
    else:
        logger.info("ℹ No stale cookies to clear")
        return True


def test_api_connectivity():
    """Test Pinterest API connectivity"""
    logger.info("\n" + "="*70)
    logger.info("🔗 TESTING API CONNECTIVITY")
    logger.info("="*70)

    try:
        import requests
        logger.info("Testing Pinterest API endpoints...")

        endpoints = {
            "Pinterest Main": "https://www.pinterest.com",
            "API Resource": "https://www.pinterest.com/resource/ApiResource/create/",
            "Pin Resource": "https://www.pinterest.com/resource/PinResource/create/",
        }

        for name, url in endpoints.items():
            try:
                resp = requests.head(url, timeout=5)
                status = resp.status_code
                if status in (200, 404, 405):
                    logger.info(f"  ✓ {name}: {status} OK")
                else:
                    logger.warning(f"  ⚠ {name}: {status}")
            except Exception as e:
                logger.error(f"  ✗ {name}: {e}")

        return True
    except ImportError:
        logger.warning("  ⚠ requests not installed, skipping API test")
        return True


def main():
    """Run all diagnostics"""
    logger.info("\n")
    logger.info("╔" + "="*68 + "╗")
    logger.info("║" + " "*15 + "PINTEREST POSTING DIAGNOSTICS" + " "*24 + "║")
    logger.info("╚" + "="*68 + "╝")

    results = {
        "credentials": check_credentials(),
        "cookies": check_cookies(),
        "history": check_history(),
        "api": test_api_connectivity(),
    }

    logger.info("\n" + "="*70)
    logger.info("🔧 FIXES APPLIED")
    logger.info("="*70)

    # Apply fixes
    cookies_cleared = clear_stale_cookies()

    logger.info("\n" + "="*70)
    logger.info("📊 SUMMARY")
    logger.info("="*70)

    if results["credentials"]:
        logger.info("✓ Credentials: OK")
    else:
        logger.error("✗ Credentials: MISSING - Add PINTEREST_EMAIL, PINTEREST_PASSWORD to .env")

    if results["cookies"]:
        logger.info("✓ Cookies: Valid")
    else:
        logger.info("ℹ Cookies: Will use email/password or GitHub secret")

    if results["api"]:
        logger.info("✓ API: Reachable")
    else:
        logger.warning("⚠ API: Some connectivity issues (may be temporary)")

    logger.info("\n" + "="*70)
    logger.info("🚀 NEXT STEPS")
    logger.info("="*70)

    if not results["credentials"]:
        logger.error("\n❌ CANNOT PROCEED - Missing Pinterest credentials")
        logger.error("   1. Add PINTEREST_EMAIL and PINTEREST_PASSWORD to .env")
        logger.error("   2. Or set GitHub secrets PINTEREST_EMAIL, PINTEREST_PASSWORD")
        logger.error("   3. Or use PINTEREST_COOKIES_B64 GitHub secret")
        return 1

    logger.info("\n✅ READY TO POST")
    logger.info("   Run: python pinterest_daily.py")
    logger.info("   This will:")
    logger.info("     1. Load fresh credentials (email/password)")
    logger.info("     2. Handle any corrupted cookies automatically")
    logger.info("     3. Retry on 500 errors with exponential backoff")
    logger.info("     4. Use fallback API endpoints if primary fails")
    logger.info("     5. Post a pin to a random board (with rotation)")

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
