"""
stealth_pinterest_poster.py — Stealth Playwright UI Automation for Pinterest

Posts pins directly via Pinterest's web UI (https://www.pinterest.com/pin-builder/)
using Playwright Chromium with anti-detection flags and human-like interactions.
Eliminates HTTP API scraping flags and shadowban issues.

Utilizes double-encryption secrets strategy (ENCRYPTION_KEY_PRIMARY & ENCRYPTION_KEY_FALLBACK).
"""

import os
import sys
import time
import json
import base64
import random
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from playwright.sync_api import sync_playwright, Page, BrowserContext, ElementHandle

# ── Double Encryption Secrets Initialization ─────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
    logging.info("[secrets] double-encryption secrets injected successfully")
except Exception as e:
    logging.warning(f"[secrets] secrets_manager fallback: {e}")
    def get_secret(key: str) -> Optional[str]:
        return os.environ.get(key)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

COOKIES_B64_FILE = ROOT / ".pinterest_cookies_b64"
COOKIES_FILE = ROOT / ".pinterest_cookies"


class StealthPinterestPoster:
    """
    Playwright-based browser UI automation for creating Pinterest pins safely.
    Acts as a real user navigating to /pin-builder/.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.username = get_secret("PINTEREST_USERNAME") or os.environ.get("PINTEREST_USERNAME", "meeeshop")
        self.email = get_secret("PINTEREST_EMAIL") or os.environ.get("PINTEREST_EMAIL", "")
        self.password = get_secret("PINTEREST_PASSWORD") or os.environ.get("PINTEREST_PASSWORD", "")

    def _get_cookies_dict(self) -> Optional[List[Dict[str, Any]]]:
        """Load cookies from env secret (PINTEREST_COOKIES_B64) or local file."""
        cookies_b64 = get_secret("PINTEREST_COOKIES_B64") or os.environ.get("PINTEREST_COOKIES_B64")
        if cookies_b64:
            try:
                cookies_json = base64.b64decode(cookies_b64.strip()).decode('utf-8-sig')
                cookies_raw = json.loads(cookies_json)
                return self._normalize_cookies(cookies_raw)
            except Exception as e:
                logger.warning(f"Failed to parse PINTEREST_COOKIES_B64: {e}")

        if COOKIES_B64_FILE.exists():
            try:
                content = COOKIES_B64_FILE.read_text(encoding='utf-8').strip()
                cookies_json = base64.b64decode(content).decode('utf-8-sig')
                cookies_raw = json.loads(cookies_json)
                return self._normalize_cookies(cookies_raw)
            except Exception as e:
                logger.warning(f"Failed to load from {COOKIES_B64_FILE.name}: {e}")

        if COOKIES_FILE.exists():
            try:
                cookies_raw = json.loads(COOKIES_FILE.read_text(encoding='utf-8'))
                return self._normalize_cookies(cookies_raw)
            except Exception as e:
                logger.warning(f"Failed to load from {COOKIES_FILE.name}: {e}")

        return None

    def _normalize_cookies(self, raw_cookies: Any) -> List[Dict[str, Any]]:
        """Normalize cookies format for Playwright context.add_cookies()."""
        normalized = []
        if isinstance(raw_cookies, dict):
            for k, v in raw_cookies.items():
                normalized.append({
                    "name": str(k),
                    "value": str(v),
                    "domain": ".pinterest.com",
                    "path": "/"
                })
        elif isinstance(raw_cookies, list):
            for c in raw_cookies:
                if isinstance(c, dict) and "name" in c and "value" in c:
                    cookie = {
                        "name": str(c["name"]),
                        "value": str(c["value"]),
                        "domain": c.get("domain", ".pinterest.com"),
                        "path": c.get("path", "/")
                    }
                    if "sameSite" in c:
                        # Normalize sameSite values for Playwright ('Strict', 'Lax', 'None')
                        ss = str(c["sameSite"]).capitalize()
                        if ss in ["Strict", "Lax", "None"]:
                            cookie["sameSite"] = ss
                    normalized.append(cookie)
        return normalized

    def _human_type(self, page: Page, selector: str, text: str):
        """Type text into field with natural human-like keystroke delays."""
        page.focus(selector)
        # Clear field if existing content
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        for char in text:
            page.keyboard.type(char, delay=random.randint(30, 85))
            if random.random() < 0.05:
                time.sleep(random.uniform(0.1, 0.3))

    def create_pin(
        self,
        image_path: str,
        title: str,
        description: str,
        board_name: str,
        link_url: str,
        alt_text: Optional[str] = None,
        dry_run: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Post a single pin via Playwright web UI automation.

        Args:
            image_path: Absolute path to image/video file
            title: Pin title (up to 100 chars)
            description: Pin description (up to 500 chars)
            board_name: Exact or target board name to select
            link_url: Store destination URL
            alt_text: Image accessibility alt text
            dry_run: If True, fills the pin builder form but stops before clicking publish

        Returns:
            Tuple of (success_bool, pin_url_or_error_msg)
        """
        img_file = Path(image_path)
        if not img_file.exists():
            return False, f"Image file not found: {image_path}"

        logger.info(f"🚀 Launching Stealth Playwright Chromium (headless={self.headless})...")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-size=1280,900",
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ]
            )

            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York"
            )

            # Mask navigator.webdriver
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            cookies = self._get_cookies_dict()
            if cookies:
                try:
                    context.add_cookies(cookies)
                    logger.info(f"✓ Injected {len(cookies)} session cookies into Playwright context")
                except Exception as e:
                    logger.warning(f"Could not inject cookies: {e}")

            page = context.new_page()

            try:
                # 1. Navigate to Pin Builder page
                logger.info("🌐 Navigating to https://www.pinterest.com/pin-builder/ ...")
                page.goto("https://www.pinterest.com/pin-builder/", wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)

                # Check if redirected to login
                if "login" in page.url:
                    logger.info("Session expired/not logged in. Attempting login via credentials...")
                    if not self._login_via_ui(page):
                        return False, "Failed to log into Pinterest via UI"
                    logger.info("Logged in! Re-navigating to pin-builder...")
                    page.goto("https://www.pinterest.com/pin-builder/", wait_until="domcontentloaded", timeout=45000)
                    time.sleep(3)

                # 2. Upload file
                logger.info(f"📁 Uploading media file: {img_file.name}")
                file_input = page.wait_for_selector('input[type="file"]', timeout=20000)
                if not file_input:
                    return False, "File input element not found in pin builder"
                file_input.set_input_files(str(img_file))
                time.sleep(3)

                # 3. Enter Title
                logger.info(f"📝 Entering title: {title[:50]}...")
                title_selector = '[aria-label="Add a title"], [data-test-id="pin-draft-title"] input, textarea[id*="pin-draft-title"]'
                try:
                    title_elem = page.wait_for_selector(title_selector, timeout=10000)
                    if title_elem:
                        title_elem.click()
                        self._human_type(page, title_selector, title[:100])
                except Exception as te:
                    logger.warning(f"Secondary title selector search: {te}")
                    page.fill('input[placeholder*="title" i], textarea[placeholder*="title" i]', title[:100])

                time.sleep(1)

                # 4. Enter Description
                logger.info("📄 Entering description...")
                desc_selector = '[aria-label="Add a detailed description"], [data-test-id="pin-draft-description"] textarea, textarea[id*="pin-draft-description"]'
                try:
                    desc_elem = page.wait_for_selector(desc_selector, timeout=10000)
                    if desc_elem:
                        desc_elem.click()
                        self._human_type(page, desc_selector, description[:500])
                except Exception as de:
                    logger.warning(f"Secondary description search: {de}")
                    page.fill('textarea[placeholder*="description" i]', description[:500])

                time.sleep(1)

                # 5. Enter Link / URL
                if link_url:
                    logger.info(f"🔗 Entering link URL: {link_url}")
                    link_selector = '[aria-label="Add a link"], [data-test-id="pin-draft-link"] input, input[id*="pin-draft-link"]'
                    try:
                        link_elem = page.wait_for_selector(link_selector, timeout=10000)
                        if link_elem:
                            link_elem.click()
                            self._human_type(page, link_selector, link_url)
                    except Exception as le:
                        logger.warning(f"Secondary link search: {le}")
                        page.fill('input[placeholder*="link" i], input[placeholder*="destination" i]', link_url)

                time.sleep(1.5)

                # 6. Select Board
                logger.info(f"📌 Selecting board: {board_name}")
                self._select_board_ui(page, board_name)
                time.sleep(2)

                if dry_run:
                    logger.info("🧪 DRY RUN MODE — Form filled successfully! Skipping Publish button click.")
                    browser.close()
                    return True, "dry_run_success"

                # 7. Click Publish
                logger.info("🚀 Clicking Publish pin button...")
                publish_btn = page.query_selector('[data-test-id="board-dropdown-save-button"], button:has-text("Save"), button:has-text("Publish")')
                if publish_btn:
                    publish_btn.click()
                    time.sleep(5)
                    logger.info("✓ Pin published successfully via Stealth UI Automation!")
                    
                    # Try to capture new cookies for saving back
                    try:
                        updated_cookies = context.cookies()
                        if updated_cookies:
                            COOKIES_FILE.write_text(json.dumps(updated_cookies, indent=2), encoding='utf-8')
                            logger.info(f"✓ Saved updated session cookies ({len(updated_cookies)})")
                    except Exception as ce:
                        logger.debug(f"Cookie save note: {ce}")

                    browser.close()
                    return True, page.url
                else:
                    logger.error("Could not find Publish/Save button on page")
                    browser.close()
                    return False, "Publish button not found"

            except Exception as e:
                logger.error(f"Error during stealth posting: {e}", exc_info=True)
                try:
                    page.screenshot(path=str(ROOT / "stealth_error_screenshot.png"))
                    logger.info("Saved error screenshot to stealth_error_screenshot.png")
                except:
                    pass
                browser.close()
                return False, str(e)

    def _login_via_ui(self, page: Page) -> bool:
        """Fallback UI login if cookies expired."""
        if not self.email or not self.password:
            logger.error("No PINTEREST_EMAIL / PINTEREST_PASSWORD available for UI login")
            return False

        try:
            page.goto("https://www.pinterest.com/login/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            page.fill('input[id="email"], input[name="id"]', self.email)
            page.fill('input[id="password"], input[name="password"]', self.password)
            page.click('button[type="submit"]')
            time.sleep(5)
            return "login" not in page.url
        except Exception as e:
            logger.error(f"UI login failed: {e}")
            return False

    def _select_board_ui(self, page: Page, board_name: str):
        """Click board dropdown selector and pick board by name."""
        try:
            board_btn = page.query_selector('[aria-label="Select board"], [data-test-id="board-dropdown-select-button"]')
            if board_btn:
                board_btn.click()
                time.sleep(1)
                search_input = page.query_selector('input[aria-label="Search boards"], input[placeholder*="Search" i]')
                if search_input:
                    search_input.fill(board_name)
                    time.sleep(1)
                board_item = page.query_selector(f'text="{board_name}"')
                if board_item:
                    board_item.click()
                    return
        except Exception as e:
            logger.warning(f"Board selection UI interaction warning: {e}")


if __name__ == "__main__":
    poster = StealthPinterestPoster(headless=True)
    logger.info("Stealth Pinterest Poster module ready.")
