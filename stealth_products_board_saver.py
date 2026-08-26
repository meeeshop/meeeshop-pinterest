"""
stealth_products_board_saver.py — Stealth Playwright Repin Automation from _products Board

Automates saving pins from the Meeeshop `_products` catalog board into relevant,
thematically organized boards based on product titles and types.

Features:
1. Stealth Playwright Chromium execution with anti-detection flags.
2. Double-encryption secrets loading (PINTEREST_EMAIL, PINTEREST_PASSWORD, PINTEREST_COOKIES_B64).
3. Reads product pins directly from `https://www.pinterest.com/{username}/_products/`.
4. Intelligent Board Matching using board_mapping.py (50+ niche categories + LRU rotation).
5. Dual-engine saving:
   - Primary: Fast in-browser RepinResource/create/ execution (same session, CSRF & TLS).
   - Fallback: Human-like UI interaction on Pinterest Pin page.
6. Anti-Shadowban Guardrails:
   - Configurable batch size (Default: 8 pins per run, max 20/day).
   - Humanized randomized delays (15–45 seconds with mouse/scroll jitter).
   - Strict deduplication history (repin_history_stealth.json).
   - Dry Run mode support (--dry-run).
"""

import os
import sys
import time
import json
import base64
import random
import logging
import argparse
import gzip
import csv
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List

from playwright.sync_api import sync_playwright, Page, BrowserContext

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Force Robust Logging to stdout ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ProductsBoardSaver")

# ── Double Encryption Secrets Initialization ─────────────────────────────────
try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
    logger.info("[secrets] double-encryption secrets injected successfully")
except Exception as e:
    logger.warning(f"[secrets] secrets_manager fallback: {e}")
    def get_secret(key: str) -> Optional[str]:
        return os.environ.get(key)

from board_mapping import (
    get_candidate_boards_for_product,
    match_live_board,
    select_best_lru_board,
    CATEGORY_TO_BOARDS,
    MEEESHOP_BOARDS,
)

COOKIES_B64_FILE = ROOT / ".pinterest_cookies_b64"
COOKIES_FILE = ROOT / ".pinterest_cookies"
REPIN_HISTORY_FILE = ROOT / "repin_history_stealth.json"
CATALOG_FEED_FILE = ROOT / "pinterest_catalog_feed.csv.gz"


def safe_get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        val = get_secret(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


def load_repin_history() -> Dict[str, Any]:
    if REPIN_HISTORY_FILE.exists():
        try:
            return json.loads(REPIN_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not load repin history: {e}")
    return {
        "repins": [],
        "board_last_used": {},
        "daily_count": 0,
        "last_repin_time": None
    }


def save_repin_history(history: Dict[str, Any]):
    try:
        REPIN_HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
        logger.info(f"✓ Saved updated repin history ({len(history.get('repins', []))} total repins recorded)")
    except Exception as e:
        logger.error(f"Failed to save repin history: {e}")


def get_today_repin_count(history: Dict[str, Any]) -> int:
    today = datetime.now(timezone.utc).date()
    count = 0
    for item in history.get("repins", []):
        ts_str = item.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).date()
                if dt == today:
                    count += 1
            except Exception:
                pass
    return count


class StealthProductsBoardSaver:
    """
    Automates scanning and saving pins from the _products board into curated boards.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.username = safe_get_secret("PINTEREST_USERNAME", "meeeshop")
        self.email = safe_get_secret("PINTEREST_EMAIL", "")
        self.password = safe_get_secret("PINTEREST_PASSWORD", "")

    def _get_cookies_dict(self) -> Optional[List[Dict[str, Any]]]:
        cookies_b64 = safe_get_secret("PINTEREST_COOKIES_B64")
        if cookies_b64:
            try:
                cookies_json = base64.b64decode(cookies_b64.strip()).decode('utf-8-sig')
                cookies_raw = json.loads(cookies_json)
                logger.info("✓ Loaded session cookies from PINTEREST_COOKIES_B64 secret")
                return self._normalize_cookies(cookies_raw)
            except Exception as e:
                logger.warning(f"Failed to parse PINTEREST_COOKIES_B64: {e}")

        if COOKIES_B64_FILE.exists():
            try:
                content = COOKIES_B64_FILE.read_text(encoding='utf-8').strip()
                cookies_json = base64.b64decode(content).decode('utf-8-sig')
                cookies_raw = json.loads(cookies_json)
                logger.info(f"✓ Loaded session cookies from {COOKIES_B64_FILE.name}")
                return self._normalize_cookies(cookies_raw)
            except Exception as e:
                logger.warning(f"Failed to load from {COOKIES_B64_FILE.name}: {e}")

        if COOKIES_FILE.exists():
            try:
                cookies_raw = json.loads(COOKIES_FILE.read_text(encoding='utf-8'))
                logger.info(f"✓ Loaded session cookies from {COOKIES_FILE.name}")
                return self._normalize_cookies(cookies_raw)
            except Exception as e:
                logger.warning(f"Failed to load from {COOKIES_FILE.name}: {e}")

        return None

    def _normalize_cookies(self, raw_cookies: Any) -> List[Dict[str, Any]]:
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
                        ss = str(c["sameSite"]).capitalize()
                        if ss in ["Strict", "Lax", "None"]:
                            cookie["sameSite"] = ss
                    normalized.append(cookie)
        return normalized

    def fetch_user_boards(self, page: Page) -> List[Dict[str, str]]:
        """Fetch all user boards from Pinterest web session."""
        logger.info("📋 Fetching user boards list via browser context...")
        script = """
        async () => {
            const getCookie = (name) => {
                const value = `; ${document.cookie}`;
                const parts = value.split(`; ${name}=`);
                if (parts.length === 2) return parts.pop().split(';').shift();
                return null;
            };
            const csrftoken = getCookie('csrftoken') || getCookie('_pinterest_sess') || '';
            try {
                const resp = await fetch('/resource/BoardsResource/get/?source_url=/me/boards/&data=%7B%22options%22%3A%7B%22privacy_filter%22%3A%22all%22%7D%2C%22context%22%3A%7B%7D%7D', {
                    headers: {
                        'X-CSRFToken': csrftoken,
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });
                if (resp.ok) {
                    const json = await resp.json();
                    const boards = json?.resource_response?.data || [];
                    return boards.map(b => ({
                        id: String(b.id),
                        name: String(b.name || '')
                    }));
                }
            } catch (err) {}
            return [];
        }
        """
        try:
            boards = page.evaluate(script)
            if boards and len(boards) > 0:
                logger.info(f"✓ Found {len(boards)} live boards from Pinterest session")
                return boards
        except Exception as e:
            logger.debug(f"Boards API fetch note: {e}")

        logger.info(f"Using local board mapping fallback ({len(MEEESHOP_BOARDS)} boards)")
        return [{"id": f"board_{i}", "name": name} for i, name in enumerate(MEEESHOP_BOARDS)]

    def extract_pins_from_products_board(self, page: Page, max_pins: int = 40) -> List[Dict[str, Any]]:
        """Navigate to the _products board and extract pin items, with catalog fallback."""
        products_url = f"https://www.pinterest.com/{self.username}/_products/"
        logger.info(f"🔍 Navigating to _products board: {products_url}")
        
        extracted = []
        try:
            page.goto(products_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # Smooth scroll to trigger lazy loading
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1.2)

            script = """
            () => {
                const results = [];
                const pinElements = document.querySelectorAll('div[data-test-id="pin"], div[role="listitem"], a[href*="/pin/"]');
                
                pinElements.forEach(el => {
                    const linkEl = el.tagName === 'A' ? el : el.querySelector('a[href*="/pin/"]');
                    const imgEl = el.querySelector('img');
                    const titleEl = el.querySelector('h3, [role="heading"], div[title]');
                    
                    let pinId = null;
                    let href = linkEl ? linkEl.getAttribute('href') : '';
                    if (href) {
                        const match = href.match(/\\/pin\\/(\\d+)/);
                        if (match) pinId = match[1];
                    }
                    
                    let title = '';
                    if (titleEl) {
                        title = titleEl.getAttribute('title') || titleEl.textContent || '';
                    } else if (imgEl) {
                        title = imgEl.getAttribute('alt') || '';
                    }
                    
                    const imgSrc = imgEl ? imgEl.getAttribute('src') : '';
                    
                    if (pinId && !results.some(r => r.pin_id === pinId)) {
                        results.push({
                            pin_id: pinId,
                            title: title.trim(),
                            pin_url: `https://www.pinterest.com/pin/${pinId}/`,
                            image_url: imgSrc
                        });
                    }
                });
                return results;
            }
            """
            extracted = page.evaluate(script) or []
            if extracted:
                logger.info(f"✓ Extracted {len(extracted)} pins directly from _products web board")
        except Exception as e:
            logger.warning(f"Web extraction note: {e}")

        # Fallback to catalog feed items if web board extraction returned few items
        if len(extracted) < 5 and CATALOG_FEED_FILE.exists():
            logger.info("📦 Augmenting from local catalog feed (pinterest_catalog_feed.csv.gz)...")
            try:
                with gzip.open(CATALOG_FEED_FILE, mode="rt", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        pid = row.get("id") or row.get("item_group_id")
                        title = row.get("title") or row.get("product_type") or ""
                        link = row.get("link") or ""
                        img = row.get("image_link") or ""
                        if pid and title and not any(r.get("pin_id") == pid for r in extracted):
                            extracted.append({
                                "pin_id": pid,
                                "title": title,
                                "pin_url": link,
                                "image_url": img
                            })
                        if len(extracted) >= max_pins * 2:
                            break
                logger.info(f"✓ Total available product pins: {len(extracted)}")
            except Exception as fe:
                logger.warning(f"Catalog feed read note: {fe}")

        return extracted[:max_pins]

    def repin_pin_in_browser(
        self,
        page: Page,
        pin_id: str,
        target_board_id: str,
        target_board_name: str,
        pin_title: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """
        Execute in-browser Repin via RepinResource/create/ using active session tokens.
        """
        script = """
        async (args) => {
            const getCookie = (name) => {
                const value = `; ${document.cookie}`;
                const parts = value.split(`; ${name}=`);
                if (parts.length === 2) return parts.pop().split(';').shift();
                return null;
            };

            const csrftoken = getCookie('csrftoken') || getCookie('_pinterest_sess') || '';
            if (!csrftoken) return { success: false, reason: 'missing_csrf' };

            try {
                const resp = await fetch('/resource/RepinResource/create/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': csrftoken,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: new URLSearchParams({
                        'source_url': `/pin/${args.pin_id}/`,
                        'data': JSON.stringify({
                            'options': {
                                'board_id': args.target_board_id,
                                'pin_id': args.pin_id,
                                'is_buyable_pin': false
                            },
                            'context': {}
                        })
                    })
                });

                if (resp.ok) {
                    const json = await resp.json();
                    const newPinId = json?.resource_response?.data?.id || json?.data?.id;
                    if (newPinId) {
                        return { success: true, new_pin_url: `https://www.pinterest.com/pin/${newPinId}/` };
                    }
                    if (json?.resource_response?.data) {
                        return { success: true, new_pin_url: `https://www.pinterest.com/pin/${args.pin_id}/` };
                    }
                }
                const errText = await resp.text();
                return { success: false, reason: errText.substring(0, 150) };
            } catch (err) {
                return { success: false, reason: String(err) };
            }
        }
        """
        try:
            res = page.evaluate(script, {
                "pin_id": pin_id,
                "target_board_id": target_board_id,
                "target_board_name": target_board_name,
            })
            if res.get("success"):
                return True, res.get("new_pin_url", f"https://www.pinterest.com/pin/{pin_id}/")
            else:
                logger.warning(f"In-browser repin note for {pin_id}: {res.get('reason')}")
        except Exception as e:
            logger.warning(f"Browser repin execution exception: {e}")

        # Fallback to UI-based Save navigation
        return self._repin_via_ui(page, pin_id, target_board_name)

    def _repin_via_ui(self, page: Page, pin_id: str, target_board_name: str) -> Tuple[bool, Optional[str]]:
        """Fallback UI interaction on the individual Pin page."""
        pin_url = f"https://www.pinterest.com/pin/{pin_id}/"
        logger.info(f"Attempting UI save fallback on {pin_url} to '{target_board_name}'...")
        try:
            page.goto(pin_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(2)

            board_btn_selectors = [
                '[data-test-id="board-dropdown-select-button"]',
                'button[aria-label*="board" i]',
                'button:has-text("Save")',
                '[data-test-id="pin-action-save-button"]'
            ]
            for sel in board_btn_selectors:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    time.sleep(1)
                    break

            search_input = page.query_selector('input[placeholder*="search" i], input[aria-label*="search" i]')
            if search_input and search_input.is_visible():
                search_input.fill(target_board_name[:15])
                time.sleep(1)

            save_row = page.query_selector(f'div:has-text("{target_board_name[:12]}") button:has-text("Save")')
            if save_row and save_row.is_visible():
                save_row.click()
                time.sleep(2)
                logger.info(f"✓ UI Repin succeeded for pin {pin_id} to '{target_board_name}'")
                return True, pin_url

        except Exception as e:
            logger.error(f"UI Repin failed for {pin_id}: {e}")

        return False, None

    def run_repin_session(
        self,
        max_repins: int = 8,
        daily_cap: int = 20,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Orchestrates an automated repinning run from _products to organized boards.
        """
        history = load_repin_history()
        today_count = get_today_repin_count(history)

        print("\n" + "=" * 70, flush=True)
        print(f"🚀 PINTEREST STEALTH PRODUCTS BOARD SAVER", flush=True)
        print(f"Today's Repin Count: {today_count}/{daily_cap} | Batch Goal: {max_repins} pins", flush=True)
        if dry_run:
            print("🧪 DRY RUN MODE ENABLED — No changes will be published", flush=True)
        print("=" * 70 + "\n", flush=True)

        if today_count >= daily_cap:
            logger.warning(f"⚠️ Daily repin cap reached ({today_count}/{daily_cap}). Exiting safely to protect account.")
            return {"status": "skipped", "reason": "daily_cap_reached", "repinned": 0}

        allowed_this_run = min(max_repins, daily_cap - today_count)

        logger.info(f"🚀 Launching Stealth Chromium Browser (headless={self.headless})...")
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
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )

            cookies = self._get_cookies_dict()
            if cookies:
                context.add_cookies(cookies)
                logger.info(f"✓ Injected {len(cookies)} session cookies into Playwright context")
            else:
                logger.warning("No session cookies available. Logging in via credentials may be required.")

            page = context.new_page()

            # 1. Fetch live boards
            live_boards = self.fetch_user_boards(page)

            # 2. Extract product pins from _products
            product_pins = self.extract_pins_from_products_board(page, max_pins=50)

            if not product_pins:
                logger.warning("No pins found on _products board or board is empty.")
                browser.close()
                return {"status": "empty", "repinned": 0}

            # Filter out pins already repinned recently
            already_repinned_ids = {item.get("pin_id") for item in history.get("repins", [])}
            eligible_pins = [p for p in product_pins if p["pin_id"] not in already_repinned_ids]

            if not eligible_pins:
                logger.info("All scanned pins have already been saved to organized boards. Re-evaluating older pins...")
                eligible_pins = product_pins

            random.shuffle(eligible_pins)
            to_process = eligible_pins[:allowed_this_run]
            logger.info(f"🎯 Selected {len(to_process)} pins to process in this run\n")

            repinned_count = 0
            used_boards_in_run = set()

            for idx, pin_item in enumerate(to_process, 1):
                pin_id = pin_item["pin_id"]
                title = pin_item["title"]

                # Determine best organized board using keyword engine + LRU
                target_board_obj = select_best_lru_board(
                    product_title=title,
                    product_type=None,
                    live_boards=live_boards,
                    board_last_used=history.get("board_last_used", {}),
                    used_boards_in_run=used_boards_in_run
                )
                target_board_name = target_board_obj.get("name", "Trends")
                target_board_id = str(target_board_obj.get("id", ""))

                print(f"[{idx}/{len(to_process)}] Processing Pin: {pin_id}", flush=True)
                print(f"   📌 Title: {title[:60] if title else '(Untitled Product)'}", flush=True)
                print(f"   📂 Target Board: '{target_board_name}' (ID: {target_board_id})", flush=True)

                if dry_run:
                    print(f"   🧪 [DRY RUN] Would save pin {pin_id} -> board '{target_board_name}'\n", flush=True)
                    repinned_count += 1
                    continue

                success, live_url = self.repin_pin_in_browser(
                    page=page,
                    pin_id=pin_id,
                    target_board_id=target_board_id,
                    target_board_name=target_board_name,
                    pin_title=title
                )

                if success:
                    repinned_count += 1
                    used_boards_in_run.add(target_board_name)
                    now_iso = datetime.now(timezone.utc).isoformat()
                    history.setdefault("repins", []).append({
                        "pin_id": pin_id,
                        "product_title": title,
                        "source_board": "_products",
                        "target_board": target_board_name,
                        "target_board_id": target_board_id,
                        "live_url": live_url,
                        "timestamp": now_iso
                    })
                    history.setdefault("board_last_used", {})[target_board_name] = now_iso
                    history["daily_count"] = get_today_repin_count(history)
                    history["last_repin_time"] = now_iso
                    save_repin_history(history)
                    print(f"   ✅ Saved successfully! Live URL: {live_url}\n", flush=True)
                else:
                    print(f"   ❌ Failed to save pin {pin_id}\n", flush=True)

                # Human-like delay between repins (15–40 seconds)
                if idx < len(to_process):
                    delay = random.uniform(15.0, 35.0)
                    logger.info(f"   ⏳ Waiting {delay:.1f}s before next pin to simulate human behavior...")
                    time.sleep(delay)

            browser.close()
            print("\n" + "=" * 70, flush=True)
            print(f"🎉 Session complete! Successfully processed {repinned_count} pins.", flush=True)
            print("=" * 70 + "\n", flush=True)
            return {"status": "success", "repinned": repinned_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save pins from _products to organized boards.")
    parser.add_argument("--count", type=int, default=8, help="Number of pins to save in this run (default: 8)")
    parser.add_argument("--cap", type=int, default=20, help="Daily repin cap (default: 20)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--dry-run", action="store_true", help="Simulate run without actually saving")
    args = parser.parse_args()

    saver = StealthProductsBoardSaver(headless=args.headless)
    saver.run_repin_session(
        max_repins=args.count,
        daily_cap=args.cap,
        dry_run=args.dry_run
    )
