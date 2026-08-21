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

    def create_carousel_pin(
        self,
        image_paths: List[str],
        title: str,
        description: str,
        board_name: str,
        link_url: str,
        alt_text: Optional[str] = None,
        dry_run: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a Pinterest Carousel Pin (2–5 sliding images).
        Uploads 1st image to reveal 'Create carousel' button, clicks it, uploads remaining slides,
        fills title, description, link URL, alt text, then publishes.
        """
        if not image_paths or len(image_paths) < 2:
            return False, "Need at least 2 images for a carousel"

        image_paths = [p for p in image_paths if Path(p).exists()][:5]
        if len(image_paths) < 2:
            return False, "Not enough valid image files for carousel"

        logger.info(f"🎠 Launching Carousel Stealth Chromium (headless={self.headless})...")

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
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            cookies = self._get_cookies_dict()
            if cookies:
                try:
                    context.add_cookies(cookies)
                    logger.info(f"✓ Injected {len(cookies)} cookies for carousel session")
                except Exception as e:
                    logger.warning(f"Cookie inject warning: {e}")

            captured_urls: List[str] = []

            def handle_response(response):
                try:
                    if any(ep in response.url for ep in ["/resource/PinResource/create/", "/v3/pins/", "PinCreateResource"]):
                        if response.status in (200, 201):
                            data = response.json()
                            pin_id = None
                            if isinstance(data, dict):
                                rdata = data.get("resource_response", {}).get("data", {}) or data.get("data", {})
                                if isinstance(rdata, dict):
                                    pin_id = rdata.get("id")
                            if pin_id:
                                purl = f"https://www.pinterest.com/pin/{pin_id}/"
                                logger.info(f"🎯 Network listener captured created Pin URL: {purl}")
                                captured_urls.append(purl)
                except Exception:
                    pass

            page = context.new_page()
            page.on("response", handle_response)

            try:
                # 1. Navigate to pin-builder
                page.goto("https://www.pinterest.com/pin-builder/", wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)

                if "login" in page.url:
                    if not self._login_via_ui(page):
                        browser.close()
                        return False, "Login failed"
                    time.sleep(2)

                # 2. Upload initial image (image_paths[0]) first into pin builder
                logger.info(f"📤 Uploading 1st image for carousel: {Path(image_paths[0]).name}")
                try:
                    file_input = page.wait_for_selector('input[type="file"]', timeout=15000)
                except Exception:
                    file_input = None

                if not file_input:
                    browser.close()
                    return False, "File input element not found in pin builder"

                file_input.set_input_files(image_paths[0])
                logger.info("✓ Uploaded initial image, waiting for preview & 'Create carousel' button...")
                time.sleep(3)

                # 3. Click "Create carousel" button (revealed after 1st image upload)
                carousel_clicked = False
                carousel_selectors = [
                    'button:has-text("Create carousel")',
                    '[data-test-id="create-carousel"]',
                    'a:has-text("Create carousel")',
                    '[aria-label*="Create carousel" i]',
                    'div:has-text("Create carousel")',
                    'span:has-text("Create carousel")',
                    'text="Create carousel"',
                ]
                for sel in carousel_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            carousel_clicked = True
                            logger.info(f"✓ Clicked 'Create carousel' via: {sel}")
                            time.sleep(2)
                            break
                    except Exception:
                        continue

                if not carousel_clicked:
                    logger.warning("Could not click 'Create carousel' button, attempting remaining images upload directly...")

                # 4. Upload remaining images (image_paths[1:])
                remaining_images = image_paths[1:]
                logger.info(f"📤 Uploading {len(remaining_images)} remaining carousel slides...")
                try:
                    inputs = page.query_selector_all('input[type="file"]')
                    target_input = inputs[-1] if inputs else file_input
                    target_input.set_input_files(remaining_images)
                    logger.info(f"✓ Successfully uploaded {len(remaining_images)} additional slides!")
                    time.sleep(3)
                except Exception as e:
                    logger.warning(f"Batch remaining upload note ({e}), uploading slide by slide...")
                    for idx, img_path in enumerate(remaining_images):
                        try:
                            inputs = page.query_selector_all('input[type="file"]')
                            target_input = inputs[-1] if inputs else file_input
                            target_input.set_input_files(img_path)
                            logger.info(f"✓ Uploaded additional slide {idx + 1}/{len(remaining_images)}")
                            time.sleep(2)
                        except Exception as se:
                            logger.warning(f"Could not upload additional slide {idx + 1}: {se}")

                time.sleep(2)

                # 5. Fill title
                logger.info(f"📝 Entering carousel title: {title[:50]}...")
                title_selectors = [
                    'textarea[id*="pin-draft-title"]',
                    '[data-test-id="pin-draft-title"] textarea',
                    'input[placeholder*="title" i]',
                    'textarea[placeholder*="title" i]',
                    '[aria-label*="title" i]',
                ]
                self._safe_fill_field(page, "title", title_selectors, title[:100])
                time.sleep(1)

                # 6. Fill description
                logger.info("📄 Entering carousel description...")
                desc_selectors = [
                    '[aria-label="Add a detailed description"]',
                    '[aria-label*="description" i]',
                    'div[data-test-id="pin-builder-description"] [contenteditable="true"]',
                    '[data-test-id="pin-draft-description"] textarea',
                    'textarea[id*="pin-draft-description"]',
                    'textarea[placeholder*="description" i]',
                    'div[contenteditable="true"][aria-label*="description" i]',
                    'div[contenteditable="true"]',
                    'div[role="textbox"]',
                ]
                self._safe_fill_field(page, "description", desc_selectors, description[:500])
                time.sleep(1)

                # 7. Fill link URL
                if link_url:
                    logger.info(f"🔗 Entering link URL: {link_url}")
                    link_triggers = [
                        'button:has-text("Add a destination link")',
                        'button:has-text("Add a link")',
                        '[aria-label="Add a destination link"]',
                    ]
                    for trigger_sel in link_triggers:
                        try:
                            trig = page.query_selector(trigger_sel)
                            if trig and trig.is_visible():
                                trig.click()
                                time.sleep(0.5)
                                break
                        except Exception:
                            pass
                    link_selectors = [
                        'input[placeholder*="link" i]',
                        'textarea[placeholder*="link" i]',
                        'input[placeholder*="destination" i]',
                        '[aria-label*="link" i]',
                    ]
                    self._safe_fill_field(page, "link URL", link_selectors, link_url)
                time.sleep(1)

                # 8. Fill Alt Text
                if alt_text:
                    logger.info(f"🏷️ Entering carousel alt text: {alt_text[:40]}...")
                    alt_triggers = [
                        'button:has-text("Add alt text")',
                        'button:has-text("Alt text")',
                        '[aria-label="Add alt text"]',
                        '[aria-label*="alt text" i]',
                        '[data-test-id="add-alt-text-button"]',
                    ]
                    for trig_sel in alt_triggers:
                        try:
                            trig = page.query_selector(trig_sel)
                            if trig and trig.is_visible():
                                trig.click()
                                time.sleep(0.5)
                                logger.info(f"✓ Clicked alt text trigger: {trig_sel}")
                                break
                        except Exception:
                            pass

                    alt_selectors = [
                        'textarea[placeholder*="alt text" i]',
                        'input[placeholder*="alt text" i]',
                        'textarea[placeholder*="Explain what people can see" i]',
                        '[aria-label*="alt text" i]',
                        '[aria-label*="Explain what people can see" i]',
                        '[data-test-id="pin-draft-alt-text"] input',
                        '[data-test-id="pin-draft-alt-text"] textarea',
                    ]
                    self._safe_fill_field(page, "alt text", alt_selectors, alt_text[:500])
                time.sleep(1)

                if dry_run:
                    logger.info("🧪 DRY RUN — Carousel form filled. Skipping publish.")
                    browser.close()
                    return True, "dry_run_carousel"

                # 9. Select board and publish
                logger.info(f"📌 Selecting board: {board_name}")
                board_result = self._select_board_ui(page, board_name)

                if board_result == "published":
                    logger.info("✓ Carousel pin auto-published via board row Save button!")
                    time.sleep(2)
                    success, live_url = self._verify_and_get_live_pin_url(page, captured_urls, context, timeout_sec=10)
                    browser.close()
                    return success, live_url

                # Manual publish click
                logger.info("🚀 Clicking Publish pin button...")
                publish_selectors = [
                    'button[data-test-id="pin-builder-save-button"]',
                    'button:has-text("Publish")',
                    '[data-test-id="save-pin-button"]',
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
                    try:
                        publish_btn.scroll_into_view_if_needed()
                        publish_btn.click(timeout=8000)
                    except Exception as e:
                        logger.warning(f"Carousel publish click intercepted ({e}), trying evaluate click...")
                        try:
                            page.evaluate("(el) => el.click()", publish_btn)
                        except Exception:
                            pass
                    time.sleep(2)

                success, live_url = self._verify_and_get_live_pin_url(page, captured_urls, context, timeout_sec=25)
                browser.close()
                return success, live_url

            except Exception as e:
                logger.error(f"Carousel posting error: {e}", exc_info=True)
                try:
                    page.screenshot(path=str(ROOT / "stealth_carousel_error.png"))
                except Exception:
                    pass
                browser.close()
                return False, str(e)

    def create_pin(
        self,

        image_path: str,
        title: str,
        description: str,
        board_name: str,
        link_url: str,
        alt_text: Optional[str] = None,
        cover_image_path: Optional[str] = None,
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

            captured_urls: List[str] = []

            def handle_response(response):
                try:
                    if any(ep in response.url for ep in ["/resource/PinResource/create/", "/v3/pins/", "PinCreateResource"]):
                        if response.status in (200, 201):
                            data = response.json()
                            pin_id = None
                            if isinstance(data, dict):
                                rdata = data.get("resource_response", {}).get("data", {}) or data.get("data", {})
                                if isinstance(rdata, dict):
                                    pin_id = rdata.get("id")
                            if pin_id:
                                purl = f"https://www.pinterest.com/pin/{pin_id}/"
                                logger.info(f"🎯 Network listener captured created Pin URL: {purl}")
                                captured_urls.append(purl)
                except Exception:
                    pass

            page = context.new_page()
            page.on("response", handle_response)

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

                # 2b. For video pins: handle "Video cover image" step
                is_video = img_file.suffix.lower() in (".mp4", ".mov", ".avi", ".webm")
                if is_video:
                    logger.info("🎬 Video detected — looking for cover image prompt...")
                    try:
                        cover_set = False

                        # Sometimes the file input for cover is already in the DOM, sometimes we must click a button first.
                        # Let's ensure the cover file input is available.
                        inputs = page.query_selector_all('input[type="file"]')
                        if len(inputs) < 2:
                            # Need to click the trigger to reveal it
                            cover_trigger_selectors = [
                                '[data-test-id="video-cover-image-upload"]',
                                'button:has-text("Choose a cover image")',
                                'button:has-text("Upload cover image")',
                                '[aria-label="Choose cover image"]',
                                '[aria-label="Video cover image"]',
                            ]
                            for csel in cover_trigger_selectors:
                                try:
                                    cel = page.query_selector(csel)
                                    if cel and cel.is_visible():
                                        cel.click()
                                        time.sleep(1)
                                        logger.info(f"✓ Clicked video cover trigger: {csel}")
                                        break
                                except Exception:
                                    continue
                            
                            # Re-fetch inputs after click
                            inputs = page.query_selector_all('input[type="file"]')

                        if len(inputs) > 1:
                            # We have the cover slot! Now get the image to upload
                            cover_upload_path = None

                            if cover_image_path and Path(cover_image_path).exists():
                                cover_upload_path = cover_image_path
                                logger.info("Using pre-supplied cover image.")
                            else:
                                # Last resort: ffmpeg extraction
                                try:
                                    import subprocess
                                    extracted = img_file.with_suffix(".cover.jpg")
                                    subprocess.run([
                                        "ffmpeg", "-y", "-i", str(img_file),
                                        "-vframes", "1", "-q:v", "2", str(extracted)
                                    ], capture_output=True, timeout=15)
                                    if extracted.exists():
                                        cover_upload_path = str(extracted)
                                        logger.info("Generated cover image via ffmpeg.")
                                except Exception as fe:
                                    logger.warning(f"ffmpeg cover frame failed: {fe}")
                            
                            if cover_upload_path:
                                inputs[1].set_input_files(cover_upload_path)
                                logger.info(f"✓ Successfully uploaded cover image: {Path(cover_upload_path).name}")
                                time.sleep(2)
                                cover_set = True
                                # Clean up extracted frame if we made one
                                if not cover_image_path or cover_upload_path != cover_image_path:
                                    Path(cover_upload_path).unlink(missing_ok=True)

                        if not cover_set:
                            logger.warning("Could not set video cover — Publish may stay disabled")
                    except Exception as ve:
                        logger.warning(f"Video cover handling error: {ve}")

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

                # 5b. Enter Alt Text (Product, Video, Blog pins)
                if alt_text:
                    logger.info(f"🏷️ Entering alt text: {alt_text[:40]}...")
                    alt_triggers = [
                        'button:has-text("Add alt text")',
                        'button:has-text("Alt text")',
                        '[aria-label="Add alt text"]',
                        '[aria-label*="alt text" i]',
                        '[data-test-id="add-alt-text-button"]',
                    ]
                    for trig_sel in alt_triggers:
                        try:
                            trig = page.query_selector(trig_sel)
                            if trig and trig.is_visible():
                                trig.click()
                                time.sleep(0.5)
                                logger.info(f"✓ Clicked alt text trigger: {trig_sel}")
                                break
                        except Exception:
                            pass

                    alt_selectors = [
                        'textarea[placeholder*="alt text" i]',
                        'input[placeholder*="alt text" i]',
                        'textarea[placeholder*="Explain what people can see" i]',
                        '[aria-label*="alt text" i]',
                        '[aria-label*="Explain what people can see" i]',
                        '[data-test-id="pin-draft-alt-text"] input',
                        '[data-test-id="pin-draft-alt-text"] textarea',
                    ]
                    self._safe_fill_field(page, "alt text", alt_selectors, alt_text[:500])
                time.sleep(1)

                # 6. Select Board
                logger.info(f"📌 Selecting board: {board_name}")
                board_result = self._select_board_ui(page, board_name)
                # board_result: "published" (auto-saved via row Save btn), "selected" (need Publish), or "failed"

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

                # 7. If board row Save button already published, skip the Publish step
                if board_result == "published":
                    logger.info("✓ Pin auto-published via board row Save button!")
                    time.sleep(2)
                    success, live_url = self._verify_and_get_live_pin_url(page, captured_urls, context, timeout_sec=10)
                    browser.close()
                    return success, live_url

                # Otherwise click the main Publish button
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
                    try:
                        publish_btn.scroll_into_view_if_needed()
                        publish_btn.click(timeout=8000)
                    except Exception as e:
                        logger.warning(f"Publish button click intercepted ({e}), trying evaluate click...")
                        try:
                            page.evaluate("(el) => el.click()", publish_btn)
                        except Exception:
                            pass
                    time.sleep(2)
                else:
                    logger.warning("No Publish button found — assuming auto-published")
                    time.sleep(2)

                success, live_url = self._verify_and_get_live_pin_url(page, captured_urls, context, timeout_sec=25)
                browser.close()
                return success, live_url

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

    def _save_cookies(self, context) -> None:
        """Save updated session cookies back to disk."""
        try:
            updated_cookies = context.cookies()
            if updated_cookies:
                COOKIES_FILE.write_text(json.dumps(updated_cookies, indent=2), encoding='utf-8')
                logger.info(f"✓ Saved updated session cookies ({len(updated_cookies)})")
        except Exception as ce:
            logger.debug(f"Cookie save note: {ce}")

    def _try_browser_api_pin_create(
        self,
        page: Page,
        title: str,
        description: str,
        link_url: str,
        board_name: str,
        alt_text: str = "",
        media_url: str = "",
    ) -> Optional[str]:
        """
        Solution 2 (Browser-API Hybrid):
        Executes a native fetch() request directly inside the logged-in Playwright browser page.
        Uses the browser's active session cookies, CSRF tokens, and TLS context.
        Returns live_pin_url if successful, or None to fall back to UI builder.
        """
        try:
            script = """
            async (args) => {
                const getCookie = (name) => {
                    const value = `; ${document.cookie}`;
                    const parts = value.split(`; ${name}=`);
                    if (parts.length === 2) return parts.pop().split(';').shift();
                    return null;
                };

                const csrftoken = getCookie('csrftoken') || getCookie('_pinterest_sess') || '';
                if (!csrftoken) return null;

                try {
                    const resp = await fetch('/resource/PinResource/create/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-CSRFToken': csrftoken,
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: new URLSearchParams({
                            'source_url': '/pin-builder/',
                            'data': JSON.stringify({
                                'options': {
                                    'title': args.title,
                                    'description': args.description,
                                    'link': args.link_url,
                                    'image_url': args.media_url,
                                    'alt_text': args.alt_text,
                                    'board_name': args.board_name
                                },
                                'context': {}
                            })
                        })
                    });

                    if (resp.ok) {
                        const json = await resp.json();
                        const pinId = json?.resource_response?.data?.id || json?.data?.id;
                        if (pinId) {
                            return `https://www.pinterest.com/pin/${pinId}/`;
                        }
                    }
                } catch (err) {
                    return null;
                }
                return null;
            }
            """
            live_url = page.evaluate(script, {
                "title": title,
                "description": description,
                "link_url": link_url,
                "board_name": board_name,
                "alt_text": alt_text,
                "media_url": media_url,
            })
            if live_url and live_url.startswith("http"):
                logger.info(f"🎯 Browser-API Hybrid created Pin successfully: {live_url}")
                return live_url
        except Exception as e:
            logger.debug(f"Browser-API hybrid attempt note: {e}")
        return None

    def _select_board_ui(self, page: Page, board_name: str) -> str:
        """
        Open board dropdown and select the board.
        Returns:
          "published"  — board row Save button was clicked (pin is already live)
          "selected"   — board was clicked/selected, still need to hit Publish
          "failed"     — could not select board
        """
        board_selectors = [
            '[data-test-id="board-dropdown-select-button"]',
            'button[aria-label="Select board"]',
            'button[aria-label*="Select board" i]',
            'button[aria-label*="Select a board" i]',
            'button[aria-label*="board" i]',
            'button:has-text("Choose board")',
            'button:has-text("Select board")',
            '[data-test-id="board-dropdown"] button',
            '[data-test-id="board-dropdown"]',
        ]
        
        board_btn = None
        for sel in board_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    board_btn = el
                    break
            except Exception:
                pass

        if not board_btn:
            for sel in board_selectors:
                try:
                    board_btn = page.wait_for_selector(sel, timeout=3000, state="visible")
                    if board_btn:
                        break
                except Exception:
                    pass

        if board_btn:
            try:
                board_btn.click()
                time.sleep(1.5)

                search_term = board_name.replace("...", "").replace('"', "").strip()
                search_input = page.query_selector(
                    'input[aria-label="Search boards"], input[placeholder*="Search" i], input[data-test-id="board-search-input"]'
                )
                if search_input:
                    search_input.fill(search_term)
                    time.sleep(1.5)

                # Wait for board list items or rows to appear
                try:
                    page.wait_for_selector('[data-test-id="board-row"], div[role="button"], div[role="listitem"]', timeout=4000)
                except Exception:
                    pass

                # Check if specific board is found
                found_row = None
                row_selectors = [
                    f'[data-test-id="board-row"]:has-text("{search_term}")',
                    f'div[role="button"]:has-text("{search_term}")',
                    f'div[role="listitem"]:has-text("{search_term}")',
                    f'div[title*="{search_term}" i]',
                ]
                for r_sel in row_selectors:
                    rows = page.query_selector_all(r_sel)
                    for r in rows:
                        if r.is_visible():
                            found_row = r
                            break
                    if found_row:
                        break

                # If not found with search, clear search and grab first available board row
                if not found_row:
                    logger.warning(f"Board '{search_term}' not found in search results. Clearing search for fallback...")
                    if search_input:
                        search_input.fill("")
                        time.sleep(1.5)
                    fallback_rows = page.query_selector_all('[data-test-id="board-row"], div[role="listitem"], div[role="button"]')
                    for r in fallback_rows:
                        if r.is_visible() and "create board" not in (r.inner_text() or "").lower():
                            found_row = r
                            break

                if found_row:
                    # Check if there is an embedded Save button inside the row
                    save_btn = found_row.query_selector('[data-test-id="board-dropdown-save-button"], button:has-text("Save")')
                    if save_btn and save_btn.is_visible():
                        save_btn.click()
                        logger.info(f"✓ Saved pin via board row button for '{board_name}' — pin is now LIVE")
                        time.sleep(2)
                        return "published"
                    else:
                        found_row.click()
                        logger.info(f"✓ Selected board row for '{board_name}' — need to click Publish")
                        time.sleep(1.5)
                        return "selected"

            except Exception as e:
                logger.warning(f"Error in board selection sequence: {e}")

        logger.warning(f"⚠️ Board selection failed for '{board_name}'")
        return "failed"

    def _verify_and_get_live_pin_url(
        self,
        page: Page,
        captured_urls: List[str],
        context: BrowserContext,
        timeout_sec: int = 25,
    ) -> Tuple[bool, str]:
        """
        Poll for post-publish confirmation and return (success, live_pin_url_or_reason).
        Combines network interceptor URLs, DOM 'See your Pin' links, page redirects, and toast/modal checks.
        """
        start_time = time.time()
        live_url = None
        success_found = False

        while time.time() - start_time < timeout_sec:
            # 1. Network response intercepted URL
            if captured_urls:
                live_url = captured_urls[-1]
                logger.info(f"🎉 Captured live Pin URL via network response payload: {live_url}")
                success_found = True
                break

            # 2. Tab URL redirection away from pin-builder
            current_url = page.url
            if "pin-builder" not in current_url and "pinterest.com/pin/" in current_url:
                live_url = current_url
                logger.info(f"🎉 Tab redirected to live Pin URL: {live_url}")
                success_found = True
                break

            # 3. Extract href from 'See your Pin' / 'View' links in DOM
            pin_link_selectors = [
                'a[href*="/pin/"]',
                'a:has-text("See your Pin")',
                'a:has-text("View Pin")',
                'a:has-text("View")',
                '[data-test-id="see-your-pin"]',
                '[data-test-id="view-pin-button"]',
                '[data-test-id="saved-to-board"] a',
            ]
            for pl_sel in pin_link_selectors:
                try:
                    link_el = page.query_selector(pl_sel)
                    if link_el:
                        href = link_el.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = "https://www.pinterest.com" + href
                            if "/pin/" in href:
                                live_url = href
                                logger.info(f"🎉 Extracted live Pin URL from DOM link ({pl_sel}): {live_url}")
                                success_found = True
                                break
                except Exception:
                    pass

            if success_found:
                break

            # 4. Success toast / modal elements visibility check
            success_ui_selectors = [
                'div:has-text("Saved to")',
                'div:has-text("Saved")',
                'div:has-text("Published")',
                'div:has-text("Your Pin is live")',
                '[data-test-id="saved-to-board"]',
                '[data-test-id="pin-builder-success-modal"]',
                '[data-test-id="pin-builder-published-toast"]',
            ]
            for su_sel in success_ui_selectors:
                try:
                    s_el = page.query_selector(su_sel)
                    if s_el and s_el.is_visible():
                        logger.info(f"✓ Found success confirmation element: {su_sel}")
                        success_found = True
                        break
                except Exception:
                    pass

            if success_found:
                break

            time.sleep(2)

        # Fallback check on full inner text of body
        if not success_found:
            try:
                body_text = page.locator("body").inner_text()
                if any(phrase in body_text for phrase in ["Saved to", "Your Pin is live", "See your Pin", "Pin published", "Saved!"]):
                    logger.info("✓ Found success text snippet in page body confirmation!")
                    success_found = True
            except Exception:
                pass

        final_url = live_url or page.url
        if success_found:
            logger.info(f"✓ Pin published successfully! Final Live URL: {final_url}")
            self._save_cookies(context)
            return True, final_url
        else:
            logger.error(f"📌 Still on pin-builder after publish. Current URL: {final_url}")
            return False, "Publish failed — still on pin-builder and no success confirmation found"


if __name__ == "__main__":
    poster = StealthPinterestPoster(headless=True)
    logger.info("Stealth Pinterest Poster module ready.")
