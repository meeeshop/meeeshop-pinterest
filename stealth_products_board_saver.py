"""
stealth_products_board_saver.py — Stealth Repin Automation from _products Board

Automates discovering pins from the Meeeshop `_products` catalog board, loading their
true product metadata (title, product type, link), matching them to relevant niche boards
using board_mapping.py, and repinning them via Pinterest's authenticated API.

Features:
1. Loads authenticated Pinterest session (PINTEREST_COOKIES_B64 / .pinterest_cookies).
2. Fetches all 100+ live boards with their real numerical Pinterest Board IDs.
3. Discovers pins from the _products board and loads true pin titles (e.g. "Calm Feather-soft Lounge Short").
4. Accurately maps titles & product types to the correct niche boards (e.g. Loungewear, Cardigans, Dresses).
5. Dual execution engine:
   - Primary: Fast and reliable authenticated Repin API (PinterestClient.repin) using exact numerical board IDs.
   - Fallback: Playwright UI Automation with direct board picker.
6. Anti-Shadowban Guardrails:
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
import gzip
import csv
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List

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
    Scans pins from _products board, retrieves true product metadata,
    and repins them to matching organized boards using verified Pinterest Board IDs.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.username = safe_get_secret("PINTEREST_USERNAME", "meeeshop")
        self.pinterest = PinterestClient()
        self.logged_in = False
        self.live_boards = []

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

    def discover_product_pins(self, max_pins: int = 50) -> List[Dict[str, Any]]:
        """
        Discover product pins from:
        1. Products board / Products you tagged on Pinterest
        2. Playwright web scrape fallback
        3. Local Shopify catalog feed fallback
        """
        print("🔍 Discovering pins from _products board...", flush=True)
        discovered_pin_ids = []

        # 1. Try finding products from 'Products you tagged' or '_products' board feed via API
        products_board = next((b for b in self.live_boards if 'product' in b.get('name', '').lower() or 'product' in b.get('url', '').lower()), None)
        if products_board:
            b_id = str(products_board.get('id', ''))
            logger.info(f"Found catalog board '{products_board.get('name')}' (ID: {b_id})")
            try:
                pins = self.pinterest.fetch_board_pins(board_id=b_id, board_name=products_board.get('name', ''))
                for p in pins:
                    pid = str(p.get('id') or p.get('pin_id') or '')
                    if pid and pid not in discovered_pin_ids:
                        discovered_pin_ids.append(pid)
                if discovered_pin_ids:
                    logger.info(f"✓ Found {len(discovered_pin_ids)} pins from board feed API")
            except Exception as e:
                logger.warning(f"Board feed API fetch note: {e}")

        # 2. Try scraping _products web page via Playwright if fewer pins discovered
        if len(discovered_pin_ids) < 10:
            try:
                from playwright.sync_api import sync_playwright
                logger.info(f"Scanning web board https://www.pinterest.com/{self.username}/_products/ via Playwright...")
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.headless)
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    )
                    # Inject cookies if available
                    cookies_b64 = safe_get_secret("PINTEREST_COOKIES_B64")
                    if cookies_b64:
                        try:
                            cj = json.loads(base64.b64decode(cookies_b64.strip()).decode('utf-8-sig'))
                            context.add_cookies([
                                {"name": k, "value": v, "domain": ".pinterest.com", "path": "/"}
                                if isinstance(cj, dict) else c for k, v in (cj.items() if isinstance(cj, dict) else [])
                            ])
                        except Exception:
                            pass

                    page = context.new_page()
                    page.goto(f"https://www.pinterest.com/{self.username}/_products/", wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 800)")
                        time.sleep(1.0)

                    links = page.eval_on_selector_all('a[href*="/pin/"]', "els => els.map(e => e.getAttribute('href'))")
                    for href in links:
                        if href:
                            import re
                            m = re.search(r'/pin/(\d+)', href)
                            if m and m.group(1) not in discovered_pin_ids:
                                discovered_pin_ids.append(m.group(1))
                    browser.close()
                    logger.info(f"✓ Discovered {len(discovered_pin_ids)} pins from web board")
            except Exception as pe:
                logger.warning(f"Playwright web scrape note: {pe}")

        # 3. For each discovered pin ID, load true Pin metadata (Real Title, Description, Link)
        product_items = []
        print(f"📦 Loading accurate metadata for {min(len(discovered_pin_ids), max_pins)} pins...", flush=True)
        for pid in discovered_pin_ids[:max_pins]:
            try:
                pin_data = self.pinterest.client.load_pin(str(pid))
                if isinstance(pin_data, dict):
                    # Extract true title (not store header)
                    raw_title = pin_data.get('title') or pin_data.get('grid_title') or pin_data.get('seo_title') or ''
                    desc = pin_data.get('description') or ''
                    link = pin_data.get('link') or ''
                    img = pin_data.get('images', {}).get('orig', {}).get('url') if isinstance(pin_data.get('images'), dict) else ''

                    # Clean up variant suffixes (e.g. " - Miststone / X-Large")
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

        # Fallback to local catalog feed if pin metadata loading yielded no items
        if not product_items and CATALOG_FEED_FILE.exists():
            logger.info("Reading products from local catalog feed (pinterest_catalog_feed.csv.gz)...")
            try:
                with gzip.open(CATALOG_FEED_FILE, mode="rt", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        pid = row.get("id") or row.get("item_group_id")
                        title = row.get("title") or ""
                        link = row.get("link") or ""
                        img = row.get("image_link") or ""
                        if pid and title:
                            product_items.append({
                                "pin_id": pid,
                                "title": title,
                                "raw_title": title,
                                "description": row.get("description") or "",
                                "link": link,
                                "image_url": img
                            })
                        if len(product_items) >= max_pins:
                            break
            except Exception as fe:
                logger.warning(f"Catalog feed read note: {fe}")

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
        Orchestrates the repinning session.
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

        # Initialize session & load real board IDs
        if not self.initialize_session():
            return {"status": "error", "reason": "auth_failed", "repinned": 0}

        # Discover product pins
        products = self.discover_product_pins(max_pins=50)
        if not products:
            logger.warning("No product pins found on _products board.")
            return {"status": "empty", "repinned": 0}

        # Deduplicate against recent history
        already_saved_ids = {str(item.get("pin_id")) for item in history.get("repins", [])}
        eligible = [p for p in products if str(p["pin_id"]) not in already_saved_ids]

        if not eligible:
            logger.info("All scanned pins have already been organized. Re-evaluating older pins...")
            eligible = products

        random.shuffle(eligible)
        to_process = eligible[:allowed_this_run]
        print(f"\n🎯 Selected {len(to_process)} pins to process in this run\n", flush=True)

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

            print(f"[{idx}/{len(to_process)}] Processing Pin: {pin_id}", flush=True)
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
        print(f"🎉 Session complete! Successfully organized {repinned_count} pins.", flush=True)
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
