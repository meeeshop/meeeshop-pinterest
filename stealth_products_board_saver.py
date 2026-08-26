"""
stealth_products_board_saver.py — Stealth Repin Automation from _products Board

Automates discovering catalog product pins directly from `https://www.pinterest.com/meeeshop/_products/`,
extracting their true Shopify metadata (title, product type, link), matching them to relevant niche boards
using board_mapping.py, and repinning them via Pinterest's authenticated API.

Features:
1. Authenticates session cookies (PINTEREST_COOKIES_B64 / .pinterest_cookies).
2. Uses Playwright with authenticated session to scroll and discover catalog pins directly on `https://www.pinterest.com/{username}/_products/`.
3. Fetches all 100+ live boards with their real numerical Pinterest Board IDs.
4. Loads true product titles for every catalog pin (e.g. "Emory Park Amber Maxi Dress", "Calm Feather-soft Lounge Short").
5. Accurately matches each product to its specific niche board (e.g. "Emory Park Clothing", "Loungewear", "Dresses").
6. Repins to target boards using verified numerical board IDs.
7. Anti-Shadowban Guardrails:
   - Default batch size: 8 pins per run (max 20/day).
   - 15–35s randomized human delays between repins.
   - Deduplication tracking in repin_history_stealth.json.
   - Full Dry-Run mode (--dry-run).
"""

import os
import sys
import time
import json
import base64
import random
import logging
import argparse
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List

from playwright.sync_api import sync_playwright

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

from pinterest_client import PinterestClient
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
    Scans pins from _products catalog board, retrieves true product metadata,
    and repins them to matching organized boards using verified Pinterest Board IDs.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.username = safe_get_secret("PINTEREST_USERNAME", "meeeshop")
        self.pinterest = PinterestClient()
        self.logged_in = False
        self.live_boards = []

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

    def initialize_session(self) -> bool:
        """Log in to Pinterest client and load all live boards with numerical IDs."""
        print("🔑 Authenticating Pinterest Client...", flush=True)
        if self.pinterest.login():
            self.logged_in = True
            logger.info("✓ Successfully authenticated with Pinterest")
            print("📋 Fetching all live Pinterest boards with numerical IDs...", flush=True)
            self.live_boards = self.pinterest.fetch_boards()
            logger.info(f"✓ Retrieved {len(self.live_boards)} live boards")
            return True
        else:
            logger.error("Failed to authenticate Pinterest Client")
            return False

    def discover_catalog_pins_from_products_board(self, max_pins: int = 50) -> List[Dict[str, Any]]:
        """
        Directly navigate to `https://www.pinterest.com/{username}/_products/`
        with session cookies to extract actual catalog product pins.
        """
        products_url = f"https://www.pinterest.com/{self.username}/_products/"
        print(f"🔍 Scanning catalog feed on {products_url} via Authenticated Stealth Browser...", flush=True)

        discovered_pin_ids = []
        try:
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

                page = context.new_page()
                page.goto(products_url, wait_until="domcontentloaded", timeout=35000)
                time.sleep(3)

                # Scroll down multiple times to trigger lazy loading of catalog pins
                logger.info("Scrolling _products catalog feed...")
                for scroll_idx in range(5):
                    page.evaluate("window.scrollBy(0, 1000)")
                    time.sleep(1.2 + random.uniform(0.1, 0.4))

                links = page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && h.includes('/pin/'))""")
                for l in links:
                    m = re.search(r'/pin/(\d+)', l)
                    if m and m.group(1) not in discovered_pin_ids:
                        discovered_pin_ids.append(m.group(1))

                browser.close()
                logger.info(f"✓ Discovered {len(discovered_pin_ids)} catalog pins directly on _products board")

        except Exception as pe:
            logger.error(f"Playwright _products board scan error: {pe}")

        # Fallback to board feed if needed
        if not discovered_pin_ids:
            logger.info("Scanning fallback feed...")
            for b in self.live_boards:
                if '_products' in b.get('url', '') or 'products you tagged' in b.get('name', '').lower():
                    pins = self.pinterest.fetch_board_pins(board_id=str(b.get('id')), board_name=b.get('name', ''))
                    for p in pins:
                        pid = str(p.get('id') or p.get('pin_id') or '')
                        if pid and pid not in discovered_pin_ids:
                            discovered_pin_ids.append(pid)

        # For each discovered catalog pin ID, load true Pin metadata (Real Title, Description, Link)
        product_items = []
        print(f"📦 Loading true product metadata for {min(len(discovered_pin_ids), max_pins)} catalog pins...", flush=True)
        for pid in discovered_pin_ids[:max_pins]:
            try:
                pin_data = self.pinterest.client.load_pin(str(pid))
                if isinstance(pin_data, dict):
                    raw_title = pin_data.get('title') or pin_data.get('grid_title') or pin_data.get('seo_title') or ''
                    desc = pin_data.get('description') or ''
                    link = pin_data.get('link') or ''
                    img = pin_data.get('images', {}).get('orig', {}).get('url') if isinstance(pin_data.get('images'), dict) else ''

                    # Strip variant suffixes (e.g. " - Miststone / X-Large" or " - Yellow Floral / M")
                    clean_title = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title

                    product_items.append({
                        "pin_id": str(pid),
                        "title": clean_title,
                        "raw_title": raw_title,
                        "description": desc,
                        "link": link,
                        "image_url": img
                    })
            except Exception as le:
                logger.warning(f"Failed to load pin {pid} metadata: {le}")

        return product_items

    def repin_product(
        self,
        pin_id: str,
        target_board_id: str,
        target_board_name: str,
        title: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Repin product pin into target board using verified numeric Pinterest Board ID.
        """
        try:
            logger.info(f"Executing repin for Pin {pin_id} to '{target_board_name}' (ID: {target_board_id})...")
            resp = self.pinterest.client.repin(board_id=str(target_board_id), pin_id=str(pin_id))

            # Validate response
            if isinstance(resp, dict):
                resource_resp = resp.get("resource_response", {})
                status = resource_resp.get("status") or resp.get("status")
                if status == "success" or "id" in resource_resp.get("data", {}) or "id" in resp.get("data", {}):
                    new_id = resource_resp.get("data", {}).get("id") or resp.get("data", {}).get("id") or pin_id
                    live_url = f"https://www.pinterest.com/pin/{new_id}/"
                    return True, live_url
                else:
                    err_msg = resource_resp.get("error", {}).get("message") or resp.get("message") or str(resp)
                    logger.warning(f"Repin API error response for {pin_id}: {err_msg}")
            elif hasattr(resp, 'status_code') and resp.status_code == 200:
                return True, f"https://www.pinterest.com/pin/{pin_id}/"

        except Exception as e:
            logger.error(f"Repin execution failed for {pin_id}: {e}")

        return False, None

    def run_repin_session(
        self,
        max_repins: int = 8,
        daily_cap: int = 20,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Orchestrates the repinning session from _products board.
        """
        history = load_repin_history()
        today_count = get_today_repin_count(history)

        print("\n" + "=" * 70, flush=True)
        print("🚀 PINTEREST STEALTH PRODUCTS BOARD SAVER", flush=True)
        print(f"Today's Repin Count: {today_count}/{daily_cap} | Batch Goal: {max_repins} pins", flush=True)
        if dry_run:
            print("🧪 DRY RUN MODE ENABLED — No changes will be published", flush=True)
        print("=" * 70 + "\n", flush=True)

        if today_count >= daily_cap:
            logger.warning(f"⚠️ Daily repin cap reached ({today_count}/{daily_cap}). Exiting safely to protect account.")
            return {"status": "skipped", "reason": "daily_cap_reached", "repinned": 0}

        allowed_this_run = min(max_repins, daily_cap - today_count)

        # 1. Initialize session & load real board IDs
        if not self.initialize_session():
            return {"status": "error", "reason": "auth_failed", "repinned": 0}

        # 2. Discover catalog product pins directly from _products
        products = self.discover_catalog_pins_from_products_board(max_pins=50)
        if not products:
            logger.warning("No catalog pins found on _products board.")
            return {"status": "empty", "repinned": 0}

        # 3. Deduplicate against recent history
        already_saved_ids = {str(item.get("pin_id")) for item in history.get("repins", [])}
        eligible = [p for p in products if str(p["pin_id"]) not in already_saved_ids]

        if not eligible:
            logger.info("All scanned catalog pins have already been organized. Re-evaluating older pins...")
            eligible = products

        random.shuffle(eligible)
        to_process = eligible[:allowed_this_run]
        print(f"\n🎯 Selected {len(to_process)} catalog pins to process in this run\n", flush=True)

        repinned_count = 0
        used_boards_in_run = set()

        for idx, item in enumerate(to_process, 1):
            pin_id = str(item["pin_id"])
            title = item.get("title", "")
            raw_title = item.get("raw_title", title)

            # Match title to best organized board using keyword engine + LRU
            target_board_obj = select_best_lru_board(
                product_title=title,
                product_type=None,
                live_boards=self.live_boards,
                board_last_used=history.get("board_last_used", {}),
                used_boards_in_run=used_boards_in_run
            )
            target_board_name = target_board_obj.get("name", "Trends")
            target_board_id = str(target_board_obj.get("id", ""))

            print(f"[{idx}/{len(to_process)}] Processing Catalog Pin: {pin_id}", flush=True)
            print(f"   📌 Product: {raw_title}", flush=True)
            print(f"   📂 Target Board: '{target_board_name}' (ID: {target_board_id})", flush=True)

            if dry_run:
                print(f"   🧪 [DRY RUN] Would save pin {pin_id} -> board '{target_board_name}' (ID: {target_board_id})\n", flush=True)
                repinned_count += 1
                continue

            success, live_url = self.repin_product(
                pin_id=pin_id,
                target_board_id=target_board_id,
                target_board_name=target_board_name,
                title=title
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

            # Human-like delay between repins (15–35 seconds)
            if idx < len(to_process):
                delay = random.uniform(15.0, 35.0)
                logger.info(f"⏳ Waiting {delay:.1f}s before next pin to simulate human behavior...")
                time.sleep(delay)

        print("\n" + "=" * 70, flush=True)
        print(f"🎉 Session complete! Successfully organized {repinned_count} catalog pins.", flush=True)
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
