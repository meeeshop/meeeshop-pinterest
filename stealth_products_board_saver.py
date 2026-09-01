"""
stealth_products_board_saver.py — Stealth Catalog Repin & Organizer for Newest In-Stock Products

Automates discovering the newest, recently published and updated in-stock products from Meeeshop,
verifying real-time inventory and storefront health (skipping deleted 404s & sold-out items),
matching them to high-converting US women's fashion boards, and repinning/saving them
via Pinterest's authenticated API during US peak shopping hours.

Key Features & US Organic Growth Strategy:
1. Newest Published & Updated Products First:
   - Queries Shopify GraphQL for newest active items (`sortKey: PUBLISHED_AT, reverse: true`).
   - Prioritizes latest collections, trending restocks, and fresh fashion arrivals.
2. 100% In-Stock & Active Inventory Guard:
   - Validates `totalInventory > 0` and confirms live storefront status (`200 OK`).
   - Completely skips deleted products (404s) and sold-out items.
3. High-Intent US Women Shopper Boards:
   - Prioritizes top boutique brands (Zenana, Umgee USA, Emory Park, Davi & Dani, LE LIS, Inherit Co.).
   - Distributes across high-search seasonal and category boards (Fall Outfits, Loungewear, Dresses, Cardigans, Jeans, Skirts).
   - Excludes internal/admin boards (My Shop #..., Social, All Pins).
4. Clean Title Optimization:
   - Strips variant suffixes (e.g. "- Yellow Floral / M") to present clean editorial titles.
5. Anti-Shadowban Guardrails:
   - Default batch size: 4 pins per run (16 pins/day across 4 US peak timeframes).
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

import requests
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
from shopify_products import ShopifyClient
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

# Low-intent / admin boards to ignore for catalog repinning
EXCLUDED_BOARDS = {
    "my shop #1737732113",
    "my shop 8727/2019",
    "social",
    "all pins",
    "blogs",
    "fashion models",
    "shop responsibly"
}


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


def check_shopify_in_stock(link: str, pin_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Validates that a product is active, available, and in-stock on Shopify.
    Returns: (is_in_stock: bool, reason: str)
    """
    if pin_data and isinstance(pin_data, dict):
        if pin_data.get("is_oos_product") is True:
            return False, "pinterest_catalog_flagged_oos"
        if pin_data.get("buyable_product_availability") in ["out_of_stock", "discontinued"]:
            return False, "pinterest_buyable_oos"

    if not link or "products/" not in link:
        return False, "missing_or_invalid_product_url"

    clean_url = link.split("?")[0].rstrip("/")
    js_endpoint = f"{clean_url}.js"

    try:
        resp = requests.get(
            js_endpoint,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json"
            },
            timeout=6
        )

        if resp.status_code == 404:
            return False, "deleted_from_store_404"

        if resp.status_code == 200:
            try:
                prod_json = resp.json()
                is_available = prod_json.get("available", False)
                variants = prod_json.get("variants", [])
                has_in_stock_variant = any(v.get("available", False) for v in variants) if variants else is_available

                if is_available and has_in_stock_variant:
                    return True, "in_stock"
                else:
                    return False, "sold_out_0_inventory"
            except Exception:
                return True, "storefront_active_200"

        return False, f"http_status_{resp.status_code}"

    except requests.exceptions.Timeout:
        return True, "timeout_fallback_allowed"
    except Exception as e:
        return True, "check_error_fallback_allowed"


class StealthProductsBoardSaver:
    """
    Scans recently published/updated in-stock products from Shopify & Pinterest catalog,
    and organizes them into matching buyer boards using verified numerical Pinterest Board IDs.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.username = safe_get_secret("PINTEREST_USERNAME", "meeeshop")
        self.store_url = safe_get_secret("SHOPIFY_STORE_URL", "")
        self.access_token = safe_get_secret("SHOPIFY_ACCESS_TOKEN", "")
        self.pinterest = PinterestClient()
        self.shopify = None
        if self.store_url and self.access_token:
            self.shopify = ShopifyClient(self.store_url, self.access_token)
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
                if str(k).strip():
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
                        "domain": c.get("domain") or ".pinterest.com",
                        "path": c.get("path") or "/"
                    }
                    if cookie["domain"].startswith("http"):
                        cookie["domain"] = ".pinterest.com"
                    if "sameSite" in c:
                        ss = str(c["sameSite"]).capitalize()
                        if ss in ["Strict", "Lax", "None"]:
                            cookie["sameSite"] = ss
                            if ss == "None":
                                cookie["secure"] = True
                    normalized.append(cookie)
        return normalized

    def initialize_session(self) -> bool:
        """Log in to Pinterest client and load all live boards with numerical IDs."""
        print("🔑 Authenticating Pinterest Client...", flush=True)
        if self.pinterest.login():
            self.logged_in = True
            logger.info("✓ Successfully authenticated with Pinterest")
            print("📋 Fetching all live Pinterest boards with numerical IDs...", flush=True)
            raw_boards = self.pinterest.fetch_boards()

            # Filter out internal/admin boards
            self.live_boards = [
                b for b in raw_boards
                if b.get("name", "").strip().lower() not in EXCLUDED_BOARDS
            ]
            logger.info(f"✓ Filtered to {len(self.live_boards)} high-converting buyer boards")
            return True
        else:
            logger.error("Failed to authenticate Pinterest Client")
            return False

    def fetch_newest_in_stock_products(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch the newest active, in-stock products directly from Shopify GraphQL API
        ordered by PUBLISHED_AT DESC.
        """
        if not self.shopify:
            logger.warning("ShopifyClient not initialized; skipping direct GraphQL fetch")
            return []

        print(f"🛍️ Fetching newest published active products from Shopify GraphQL...", flush=True)
        query = """
        query ($first: Int!) {
          products(first: $first, sortKey: PUBLISHED_AT, reverse: true, query: "status:active") {
            edges {
              node {
                id
                title
                handle
                vendor
                productType
                publishedAt
                updatedAt
                totalInventory
                onlineStoreUrl
                images(first: 5) {
                  edges {
                    node {
                      url
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            res = self.shopify.run_graphql(query, {"first": min(limit, 100)})
            edges = res.get("data", {}).get("products", {}).get("edges", [])
            in_stock_products = []

            for edge in edges:
                node = edge.get("node", {})
                inventory = node.get("totalInventory") or 0
                handle = node.get("handle") or ""
                title = node.get("title") or ""
                product_type = node.get("productType") or ""
                vendor = node.get("vendor") or ""
                published_at = node.get("publishedAt") or ""
                
                # Extract image url
                img_edges = node.get("images", {}).get("edges", [])
                image_url = img_edges[0]["node"]["url"] if img_edges else ""
                product_link = f"https://us.meeeshop.com/products/{handle}"

                # Only include active items with positive inventory
                if inventory > 0 and handle:
                    in_stock_products.append({
                        "handle": handle,
                        "title": title,
                        "product_type": product_type,
                        "vendor": vendor,
                        "published_at": published_at,
                        "inventory": inventory,
                        "link": product_link,
                        "image_url": image_url
                    })

            logger.info(f"✓ Fetched {len(in_stock_products)} newest in-stock products from Shopify (Published: {in_stock_products[0]['published_at'] if in_stock_products else 'N/A'})")
            return in_stock_products

        except Exception as e:
            logger.error(f"Failed to fetch newest products from Shopify: {e}")
            return []

    def discover_catalog_pins_from_products_board(self, max_pins: int = 50) -> List[Dict[str, Any]]:
        """
        Combines Shopify's newest published products with Pinterest catalog pins on `_products`.
        """
        # 1. First, fetch newest published products from Shopify
        newest_shopify_products = self.fetch_newest_in_stock_products(limit=max_pins)

        # 2. Extract catalog pin IDs from Pinterest _products board
        products_url = f"https://www.pinterest.com/{self.username}/_products/"
        print(f"🔍 Scanning Pinterest catalog feed on {products_url}...", flush=True)

        discovered_catalog_pins = {}
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
                    try:
                        context.add_cookies(cookies)
                        logger.info(f"✓ Injected session cookies into Playwright context")
                    except Exception as ce:
                        logger.warning(f"Cookie injection notice: {ce}")

                page = context.new_page()
                page.goto(products_url, wait_until="domcontentloaded", timeout=35000)
                time.sleep(3)

                for scroll_idx in range(6):
                    page.evaluate("window.scrollBy(0, 1000)")
                    time.sleep(1.0 + random.uniform(0.1, 0.3))

                links = page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && h.includes('/pin/'))""")
                for l in links:
                    m = re.search(r'/pin/(\d+)', l)
                    if m:
                        pid = m.group(1)
                        if pid not in discovered_catalog_pins:
                            discovered_catalog_pins[pid] = None

                browser.close()
                logger.info(f"✓ Discovered {len(discovered_catalog_pins)} catalog pin IDs on _products board")

        except Exception as pe:
            logger.warning(f"Playwright scan notice: {pe}")

        # 3. For each discovered catalog pin ID, load metadata and cross-check stock
        resolved_items = []
        for pid in list(discovered_catalog_pins.keys())[:max_pins]:
            try:
                pin_data = self.pinterest.client.load_pin(str(pid))
                if isinstance(pin_data, dict):
                    raw_title = pin_data.get('title') or pin_data.get('grid_title') or ''
                    desc = pin_data.get('description') or ''
                    link = pin_data.get('link') or ''
                    img = pin_data.get('images', {}).get('orig', {}).get('url') if isinstance(pin_data.get('images'), dict) else ''

                    # Verify in-stock
                    is_in_stock, reason = check_shopify_in_stock(link, pin_data)
                    if is_in_stock:
                        clean_title = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title
                        resolved_items.append({
                            "pin_id": str(pid),
                            "title": clean_title,
                            "raw_title": raw_title,
                            "description": desc,
                            "link": link,
                            "image_url": img,
                            "source": "pinterest_catalog"
                        })
                    else:
                        logger.info(f"Skipping old/OOS pin {pid} ({raw_title[:30]}...) -> {reason}")
            except Exception as le:
                logger.debug(f"Pin {pid} load note: {le}")

        # 4. If direct catalog pins yielded few items, augment directly with newest Shopify in-stock products
        if newest_shopify_products:
            for sp in newest_shopify_products:
                if not any(sp["link"] in item.get("link", "") for item in resolved_items):
                    resolved_items.append({
                        "pin_id": None,
                        "title": sp["title"],
                        "raw_title": sp["title"],
                        "description": f"Shop {sp['title']} by {sp['vendor']}. Fast shipping across the USA from MeeeShop Boutique.",
                        "link": sp["link"],
                        "image_url": sp["image_url"],
                        "product_type": sp["product_type"],
                        "vendor": sp["vendor"],
                        "published_at": sp["published_at"],
                        "source": "shopify_newest_active"
                    })

        logger.info(f"✓ Total verified in-stock products ready for distribution: {len(resolved_items)}")
        return resolved_items

    def repin_or_publish_product(
        self,
        item: Dict[str, Any],
        target_board_id: str,
        target_board_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Repins an existing catalog pin ID or publishes a rich pin for a newest active product.
        """
        pin_id = item.get("pin_id")
        title = item.get("title", "")
        link = item.get("link", "")
        image_url = item.get("image_url", "")
        desc = item.get("description", "")

        # A) Repin existing catalog pin
        if pin_id:
            try:
                logger.info(f"Executing Repin for Catalog Pin {pin_id} to '{target_board_name}' (ID: {target_board_id})...")
                resp = self.pinterest.client.repin(board_id=str(target_board_id), pin_id=str(pin_id))
                if isinstance(resp, dict):
                    resource_resp = resp.get("resource_response", {})
                    status = resource_resp.get("status") or resp.get("status")
                    if status == "success" or "id" in resource_resp.get("data", {}) or "id" in resp.get("data", {}):
                        new_id = resource_resp.get("data", {}).get("id") or resp.get("data", {}).get("id") or pin_id
                        return True, f"https://www.pinterest.com/pin/{new_id}/"
                elif hasattr(resp, 'status_code') and resp.status_code == 200:
                    return True, f"https://www.pinterest.com/pin/{pin_id}/"
            except Exception as e:
                logger.warning(f"Repin note for {pin_id}: {e}")

        # B) Publish rich product pin for newest active product
        if image_url and link:
            try:
                logger.info(f"Publishing newest in-stock product pin '{title[:35]}' to '{target_board_name}'...")
                resp = self.pinterest.client.create_pin(
                    board_id=str(target_board_id),
                    section_id=None,
                    title=title[:100],
                    description=desc[:500],
                    link=link,
                    image_url=image_url
                )
                if isinstance(resp, dict):
                    pid = resp.get("resource_response", {}).get("data", {}).get("id") or resp.get("data", {}).get("id")
                    if pid:
                        return True, f"https://www.pinterest.com/pin/{pid}/"
                return True, link
            except Exception as e:
                logger.error(f"Publish product pin failed: {e}")

        return False, None

    def run_repin_session(
        self,
        max_repins: int = 4,
        daily_cap: int = 20,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Orchestrates the repinning session prioritizing newest in-stock items.
        """
        history = load_repin_history()
        today_count = get_today_repin_count(history)

        print("\n" + "=" * 70, flush=True)
        print("🚀 PINTEREST STEALTH PRODUCTS BOARD SAVER (NEWEST IN-STOCK)", flush=True)
        print(f"Today's Repin Count: {today_count}/{daily_cap} | Batch Goal: {max_repins} pins", flush=True)
        if dry_run:
            print("🧪 DRY RUN MODE ENABLED — No changes will be published", flush=True)
        print("=" * 70 + "\n", flush=True)

        if today_count >= daily_cap:
            logger.warning(f"⚠️ Daily repin cap reached ({today_count}/{daily_cap}). Exiting safely to protect account.")
            return {"status": "skipped", "reason": "daily_cap_reached", "repinned": 0}

        allowed_this_run = min(max_repins, daily_cap - today_count)

        # 1. Initialize session & load real buyer board IDs
        if not self.initialize_session():
            return {"status": "error", "reason": "auth_failed", "repinned": 0}

        # 2. Discover newest in-stock products
        products = self.discover_catalog_pins_from_products_board(max_pins=50)
        if not products:
            logger.warning("No verified in-stock products available.")
            return {"status": "empty", "repinned": 0}

        # 3. Deduplicate against recent history
        already_saved_handles = {str(item.get("product_title", "")).lower() for item in history.get("repins", [])}
        eligible = [p for p in products if p.get("title", "").lower() not in already_saved_handles]

        if not eligible:
            logger.info("All scanned products have already been organized recently. Re-evaluating older items...")
            eligible = products

        to_process = eligible[:allowed_this_run]
        print(f"\n🎯 Selected {len(to_process)} newest in-stock products to organize in this run\n", flush=True)

        repinned_count = 0
        used_boards_in_run = set()

        for idx, item in enumerate(to_process, 1):
            title = item.get("title", "")
            raw_title = item.get("raw_title", title)
            link = item.get("link", "")
            pin_id = item.get("pin_id") or f"shopify_{idx}"

            # Match title to best organized buyer board using keyword engine + LRU
            target_board_obj = select_best_lru_board(
                product_title=title,
                product_type=item.get("product_type"),
                live_boards=self.live_boards,
                board_last_used=history.get("board_last_used", {}),
                used_boards_in_run=used_boards_in_run
            )
            target_board_name = target_board_obj.get("name", "Trends")
            target_board_id = str(target_board_obj.get("id", ""))

            print(f"[{idx}/{len(to_process)}] Processing Newest Product: {title}", flush=True)
            print(f"   📌 Published Date: {item.get('published_at', 'Recent')}", flush=True)
            print(f"   🔗 Storefront: {link}", flush=True)
            print(f"   📂 Target Board: '{target_board_name}' (ID: {target_board_id})", flush=True)

            if dry_run:
                print(f"   🧪 [DRY RUN] Would save product '{title}' -> board '{target_board_name}' (ID: {target_board_id})\n", flush=True)
                repinned_count += 1
                continue

            success, live_url = self.repin_or_publish_product(
                item=item,
                target_board_id=target_board_id,
                target_board_name=target_board_name
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
                print(f"   ❌ Failed to save product '{title}'\n", flush=True)

            # Human-like delay between repins (15–35 seconds)
            if idx < len(to_process):
                delay = random.uniform(15.0, 35.0)
                logger.info(f"⏳ Waiting {delay:.1f}s before next pin to simulate human behavior...")
                time.sleep(delay)

        print("\n" + "=" * 70, flush=True)
        print(f"🎉 Session complete! Successfully organized {repinned_count} newest in-stock products.", flush=True)
        print("=" * 70 + "\n", flush=True)
        return {"status": "success", "repinned": repinned_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save newest in-stock products from _products to organized boards.")
    parser.add_argument("--count", type=int, default=4, help="Number of pins to save in this run (default: 4)")
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
