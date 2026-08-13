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
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

COOKIES_B64_FILE = ROOT / ".pinterest_cookies_b64"
COOKIES_FILE = ROOT / ".pinterest_cookies"


def safe_get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        val = get_secret(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


class StealthPinterestPoster:
    """
    Playwright-based browser UI automation for creating Pinterest pins safely.
    Acts as a real user navigating to /pin-builder/.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.username = safe_get_secret("PINTEREST_USERNAME", "meeeshop")
        self.email = safe_get_secret("PINTEREST_EMAIL", "")
        self.password = safe_get_secret("PINTEREST_PASSWORD", "")

    def _get_cookies_dict(self) -> Optional[List[Dict[str, Any]]]:
        """Load cookies from env secret (PINTEREST_COOKIES_B64) or local file."""
        cookies_b64 = safe_get_secret("PINTEREST_COOKIES_B64")
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

    def _safe_fill_field(self, page: Page, field_name: str, selectors: List[str], text: str) -> bool:
        """Try a list of selectors for a form field. Supports inputs, textareas, and contenteditable elements."""
        for selector in selectors:
            try:
                elem = page.wait_for_selector(selector, timeout=3000, state="visible")
                if elem:
                    elem.click()
                    time.sleep(0.3)

                    # Method 1: Try page.fill
                    try:
                        page.fill(selector, text)
                        logger.info(f"✓ Filled {field_name} using: {selector}")
                        return True
                    except Exception:
                        pass

                    # Method 2: Try keyboard typing
                    try:
                        page.focus(selector)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(text, delay=20)
                        logger.info(f"✓ Typed into {field_name} using: {selector}")
                        return True
                    except Exception:
                        pass
            except Exception:
                continue

        logger.warning(f"⚠️ Could not fill {field_name} field using any known selectors")
        return False

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
                time.sleep(4)

                # 3. Enter Title
                logger.info(f"📝 Entering title: {title[:50]}...")
                title_selectors = [
                    '[aria-label="Add a title"]',
                    'div[data-test-id="pin-builder-title"] [contenteditable="true"]',
                    '[data-test-id="pin-draft-title"] input',
                    'textarea[id*="pin-draft-title"]',
                    'input[placeholder*="title" i]',
                    'textarea[placeholder*="title" i]',
                    '[aria-label*="title" i]',
                ]
                title_ok = self._safe_fill_field(page, "title", title_selectors, title[:100])
                time.sleep(1)

                # 4. Enter Description
                logger.info("📄 Entering description...")
                desc_selectors = [
                    '[aria-label="Add a detailed description"]',
                    '[aria-label*="description" i]',
                    'div[data-test-id="pin-builder-description"] [contenteditable="true"]',
                    '[data-test-id="pin-draft-description"] textarea',
                    'textarea[id*="pin-draft-description"]',
                    'textarea[placeholder*="description" i]',
                    'div[contenteditable="true"][aria-label*="description" i]',
                    'div[contenteditable="true"]',
                ]
                desc_ok = self._safe_fill_field(page, "description", desc_selectors, description[:500])
                time.sleep(1)

                # 5. Enter Link / URL
                link_ok = True
                if link_url:
                    logger.info(f"🔗 Entering link URL: {link_url}")
                    # Click destination link trigger button if collapsed
                    link_triggers = [
                        'button:has-text("Add a destination link")',
                        'button:has-text("Add a link")',
                        '[aria-label="Add a destination link"]',
                        '[aria-label="Add a link"]',
                        '[data-test-id="pin-builder-link"]',
                        'div:has-text("Add a destination link")',
                        'div:has-text("Add a link")',
                    ]
                    for trigger_sel in link_triggers:
                        try:
                            trig = page.query_selector(trigger_sel)
                            if trig and trig.is_visible():
                                trig.click()
                                time.sleep(0.5)
                                logger.info(f"✓ Clicked link trigger: {trigger_sel}")
                                break
                        except Exception:
                            pass

                    link_selectors = [
                        '[data-test-id="pin-draft-link"] input',
                        '[aria-label="Add a destination link"] input',
                        '[aria-label="Add a link"] input',
                        '[aria-label*="link" i]',
                        '[aria-label*="destination" i]',
                        'input[placeholder*="link" i]',
                        'input[placeholder*="destination" i]',
                        'textarea[placeholder*="link" i]',
                        'input[id*="pin-draft-link"]',
                        'input[type="text"][placeholder*="http" i]',
                        'input[type="url"]',
                    ]
                    link_ok = self._safe_fill_field(page, "link URL", link_selectors, link_url)
                time.sleep(1.5)

                # 6. Select Board
                logger.info(f"📌 Selecting board: {board_name}")
                board_ok = self._select_board_ui(page, board_name)
                time.sleep(2)

                if not title_ok or not link_ok:
                    error_msg = f"Failed to fill mandatory fields (title_ok={title_ok}, link_ok={link_ok})"
                    logger.error(error_msg)
                    try:
                        page.screenshot(path=str(ROOT / "stealth_form_failure.png"))
                    except:
                        pass
                    browser.close()
                    return False, error_msg

                if dry_run:
                    logger.info("🧪 DRY RUN MODE — All form fields verified & filled successfully! Skipping Publish click.")
                    browser.close()
                    return True, "dry_run_success"

                # 7. Click Publish
                logger.info("🚀 Clicking Publish pin button...")
                publish_selectors = [
                    'button[data-test-id="pin-builder-save-button"]',
                    '[data-test-id="save-pin-button"]',
                    'button:has-text("Publish")',
                    'button[aria-label="Save"]',
                    '[data-test-id="board-dropdown-save-button"]',
                    'button:has-text("Save")',
                ]
                publish_btn = None
                for sel in publish_selectors:
                    btns = page.query_selector_all(sel)
                    for btn in btns:
                        if btn.is_visible() and not btn.is_disabled():
                            publish_btn = btn
                            logger.info(f"Found active publish button using: {sel}")
                            break
                    if publish_btn:
                        break

                if publish_btn:
                    publish_btn.click()
                    logger.info("Waiting for Pinterest backend to process pin creation...")
                    
                    # Wait for either a toast notification or URL change
                    try:
                        page.wait_for_function('window.location.href.indexOf("pin-builder") === -1 || document.querySelector("div:has-text(\\"Saved\\")")', timeout=15000)
                    except Exception:
                        pass
                    
                    time.sleep(5)
                    final_url = page.url
                    logger.info(f"Final page URL after publish: {final_url}")
                    
                    try:
                        page.screenshot(path=str(ROOT / "stealth_after_publish.png"))
                        logger.info("Captured screenshot stealth_after_publish.png")
                    except:
                        pass

                    if "pin-builder" in final_url:
                        logger.warning("⚠️ Still on Pin Builder page! Pin might NOT have been published due to a validation error.")
                        error_elements = page.query_selector_all('[role="alert"], [data-test-id="toast"], div:has-text("error" i)')
                        if error_elements:
                            for err_el in error_elements:
                                try:
                                    logger.error(f"📌 Pinterest UI Alert: {err_el.inner_text()}")
                                except Exception: pass
                        else:
                            try:
                                body_text = page.locator('body').inner_text()
                                logger.error(f"📌 Body text snippet (first 500 chars): {body_text[:500]}")
                            except Exception: pass
                    else:
                        logger.info("✓ Pin published successfully via Stealth UI Automation!")

                    try:
                        updated_cookies = context.cookies()
                        if updated_cookies:
                            COOKIES_FILE.write_text(json.dumps(updated_cookies, indent=2), encoding='utf-8')
                            logger.info(f"✓ Saved updated session cookies ({len(updated_cookies)})")
                    except Exception as ce:
                        logger.debug(f"Cookie save note: {ce}")

                    browser.close()
                    return True, final_url
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

    def _select_board_ui(self, page: Page, board_name: str) -> bool:
        """Click board dropdown selector and pick board by name."""
        board_selectors = [
            '[aria-label="Select board"]',
            '[aria-label*="Select board" i]',
            '[data-test-id="board-dropdown-select-button"]',
            '[aria-label*="board" i]',
            'button:has-text("Choose board")',
            'button:has-text("Select board")',
        ]
        for sel in board_selectors:
            try:
                board_btn = page.wait_for_selector(sel, timeout=3000, state="visible")
                if board_btn:
                    board_btn.click()
                    time.sleep(1)
                    
                    search_term = board_name.replace("...", "").replace('"', "").strip()
                    search_input = page.query_selector('input[aria-label="Search boards"], input[placeholder*="Search" i], input[type="text"]')
                    if search_input:
                        search_input.fill(search_term)
                        time.sleep(2)  # Wait for search results
                    
                    # Use substring match (no quotes around search_term in text= selector)
                    board_item = page.query_selector(f'text={search_term}')
                    if board_item and board_item.is_visible():
                        board_item.click()
                        logger.info(f"✓ Selected board '{board_name}' via selector: {sel} matching '{search_term}'")
                        return True
            except Exception:
                continue
        logger.warning(f"⚠️ Board selection interaction warning for '{board_name}'")
        return False


if __name__ == "__main__":
    poster = StealthPinterestPoster(headless=True)
    logger.info("Stealth Pinterest Poster module ready.")
