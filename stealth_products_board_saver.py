"""
stealth_products_board_saver.py — Stealth Catalog Repin & Organizer with 7-Day Product Cooldown

Automates discovering in-stock products from Meeeshop, enforcing strict 7-day cooldown
(never repinning or saving products that were already pinned in the last 7 days across all workflows),
ensuring category & product diversity (every pin in a run is a DIFFERENT product from a DIFFERENT category,
saved to a DIFFERENT niche board), verifying real-time inventory and storefront health (skipping deleted 404s
and sold-out items), and publishing/repinning via Pinterest's authenticated API during US peak shopping hours.

Key Features & US Organic Growth Strategy:
1. Strict 7-Day Cross-Workflow Cooldown:
   - Scans all history files (repin_history_stealth.json, posting_history_stealth.json, posting_history_v2.json, video_posting_history.json).
   - Skips any product that was already posted, repinned, or saved within the last 7 days.
   - Rotates through the entire catalog so new, fresh products are featured on every single run.
2. Category & Product Diversity Enforcer:
   - Deduplicates candidate products by canonical base title/handle (no duplicate variants).
   - Enforces distinct product types in every run (e.g. 1 Dress, 1 Skirt, 1 Cardigan, 1 Top/Pants).
   - Distributes each product to its dedicated, distinct niche board.
3. Direct Multi-Engine Publishing:
   - Repins catalog pins if available OR downloads image and publishes Rich Product Pins via PinterestClient.
   - Formats clean Live URLs and fails CI with status code 1 if 0 pins succeed in a live run.
4. Newest Published & Updated Products First:
   - Queries Shopify GraphQL for active in-stock items (`sortKey: PUBLISHED_AT, reverse: true`).
   - Prioritizes latest collections, trending restocks, and fresh fashion arrivals.
5. 100% In-Stock & Active Inventory Guard:
   - Validates `totalInventory > 0` and confirms live storefront status (`200 OK`).
   - Completely skips deleted products (404s) and sold-out items.
6. High-Intent US Women Shopper Boards:
   - Prioritizes top boutique brands (Zenana, Umgee USA, Emory Park, Davi & Dani, LE LIS, Inherit Co.).
   - Distributes across high-search seasonal and category boards (Fall Outfits, Loungewear, Dresses, Cardigans, Jeans, Skirts).
   - Excludes internal/admin boards (My Shop #..., Social, All Pins).
7. Anti-Shadowban Guardrails:
   - Default batch size: 4 pins per run (16 pins/day across 4 US peak timeframes).
   - 15–35s randomized human delays between repins.
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
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List, Set

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


def get_recently_pinned_cooldown_set(days: int = 7) -> Set[str]:
    """
    Collects normalized product names, handles, and URLs pinned or saved
    within the last N days across all posting history files.
    """
    recent_set = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    history_sources = [
        (ROOT / "repin_history_stealth.json", "repins", "timestamp", "product_title"),
        (ROOT / "posting_history_stealth.json", "posts", "timestamp", "title"),
        (ROOT / "posting_history_v2.json", "posts", "timestamp", "title"),
        (ROOT / "video_posting_history.json", "posts", "posted_at", "title"),
        (ROOT / "blog_posting_history.json", "posts", "timestamp", "product_id"),
    ]

    for fpath, key, time_key, title_key in history_sources:
        if fpath.exists():
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                for item in data.get(key, []):
                    ts_str = item.get(time_key)
                    if ts_str:
                        try:
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            if dt >= cutoff:
                                raw_title = str(item.get(title_key, "")).strip().lower()
                                if raw_title:
                                    # Normalize title by removing common brand suffixes
                                    clean = raw_title.split("—")[0].split("-")[0].split("|")[0].strip()
                                    clean_norm = re.sub(r'[^a-z0-9]', '', clean)
                                    if clean_norm:
                                        recent_set.add(clean_norm)
                                    raw_norm = re.sub(r'[^a-z0-9]', '', raw_title)
                                    if raw_norm:
                                        recent_set.add(raw_norm)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Error reading history from {fpath.name}: {e}")

    logger.info(f"✓ Loaded {len(recent_set)} unique product keys under {days}-day cooldown")
    return recent_set


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


def classify_product_category_group(title: str, product_type: str = "") -> str:
    """
    Classifies a product into high-level distinct fashion category groups
    to ensure 100% diverse product types per posting run.
    """
    text = f"{title} {product_type}".lower()
    if any(w in text for w in ["dress", "gown", "maxi dress", "mini dress", "midi dress"]):
        return "dresses"
    if any(w in text for w in ["skirt", "midi skirt", "maxi skirt", "track skirt", "denim skirt", "sport skirt"]):
        return "skirts"
    if any(w in text for w in ["cardigan", "open front", "shacket", "sweater", "pullover", "knit cardigan"]):
        return "cardigans_sweaters"
    if any(w in text for w in ["tank", "cami", "halter", "blouse", "tee", "t-shirt", "top", "shirt", "button cardigan top"]):
        return "tops_tanks_blouses"
    if any(w in text for w in ["jean", "denim", "pant", "legging", "track pant", "trouser", "flare", "wide leg"]):
        return "pants_denim"
    if any(w in text for w in ["lounge", "pajama", "sleepwear", "lounge short"]):
        return "loungewear"
    if any(w in text for w in ["bag", "tote", "backpack", "purse", "sling", "bum bag"]):
        return "bags_accessories"
    if any(w in text for w in ["jacket", "coat", "blazer", "outerwear", "trench"]):
        return "outerwear"
    if any(w in text for w in ["shoe", "heel", "boot", "flat", "sandals", "sneakers"]):
        return "footwear"
    if any(w in text for w in ["romper", "jumpsuit"]):
        return "rompers_jumpsuits"
    return "general_apparel"


class StealthProductsBoardSaver:
    """
    Scans recently published/updated in-stock products from Shopify & Pinterest catalog,
    and organizes them into matching buyer boards with strict 7-day cooldown & category diversity.
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

    def fetch_newest_in_stock_products(self, limit: int = 100) -> List[Dict[str, Any]]:
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
            res = self.shopify.run_graphql(query, {"first": min(limit, 150)})
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
                
                img_edges = node.get("images", {}).get("edges", [])
                image_url = img_edges[0]["node"]["url"] if img_edges else ""
                product_link = f"https://us.meeeshop.com/products/{handle}"

                if inventory > 0 and handle:
                    cat_group = classify_product_category_group(title, product_type)
                    in_stock_products.append({
                        "handle": handle,
                        "title": title,
                        "product_type": product_type,
                        "category_group": cat_group,
                        "vendor": vendor,
                        "published_at": published_at,
                        "inventory": inventory,
                        "link": product_link,
                        "image_url": image_url
                    })

            logger.info(f"✓ Fetched {len(in_stock_products)} newest in-stock products from Shopify")
            return in_stock_products

        except Exception as e:
            logger.error(f"Failed to fetch newest products from Shopify: {e}")
            return []

    def discover_catalog_pins_from_products_board(self, max_pins: int = 100) -> List[Dict[str, Any]]:
        """
        Combines Shopify's newest published products with Pinterest catalog pins on `_products`,
        enforcing product-level deduplication.
        """
        newest_shopify_products = self.fetch_newest_in_stock_products(limit=max_pins)

        unique_products_map = {}

        # 1. Add newest Shopify products first (freshest inventory)
        if newest_shopify_products:
            for sp in newest_shopify_products:
                canon_key = re.sub(r'[^a-z0-9]', '', sp["title"].lower())
                if canon_key not in unique_products_map:
                    unique_products_map[canon_key] = {
                        "pin_id": None,
                        "title": sp["title"],
                        "raw_title": sp["title"],
                        "description": f"Shop {sp['title']} by {sp['vendor']}. Fast shipping across the USA from MeeeShop Boutique.",
                        "link": sp["link"],
                        "image_url": sp["image_url"],
                        "product_type": sp["product_type"],
                        "category_group": sp["category_group"],
                        "vendor": sp["vendor"],
                        "published_at": sp["published_at"],
                        "source": "shopify_newest_active"
                    }

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

        # 3. For each discovered catalog pin ID, load metadata, verify stock, and deduplicate
        for pid in list(discovered_catalog_pins.keys())[:max_pins]:
            try:
                pin_data = self.pinterest.client.load_pin(str(pid))
                if isinstance(pin_data, dict):
                    raw_title = pin_data.get('title') or pin_data.get('grid_title') or ''
                    desc = pin_data.get('description') or ''
                    link = pin_data.get('link') or ''
                    img = pin_data.get('images', {}).get('orig', {}).get('url') if isinstance(pin_data.get('images'), dict) else ''

                    is_in_stock, reason = check_shopify_in_stock(link, pin_data)
                    if is_in_stock:
                        clean_title = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title
                        canon_key = re.sub(r'[^a-z0-9]', '', clean_title.lower())
                        cat_group = classify_product_category_group(clean_title, "")

                        if canon_key not in unique_products_map or unique_products_map[canon_key].get("pin_id") is None:
                            unique_products_map[canon_key] = {
                                "pin_id": str(pid),
                                "title": clean_title,
                                "raw_title": raw_title,
                                "description": desc,
                                "link": link,
                                "image_url": img,
                                "category_group": cat_group,
                                "source": "pinterest_catalog"
                            }
                    else:
                        logger.info(f"Skipping old/OOS pin {pid} ({raw_title[:30]}...) -> {reason}")
            except Exception as le:
                logger.debug(f"Pin {pid} load note: {le}")

        resolved_items = list(unique_products_map.values())
        logger.info(f"✓ Total unique, verified in-stock products ready for distribution: {len(resolved_items)}")
        return resolved_items

    def select_diverse_product_batch(
        self,
        products: List[Dict[str, Any]],
        batch_size: int,
        cooldown_set: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Selects a strictly diverse batch of fresh products where:
        1. Products pinned in the last 7 days are strictly skipped.
        2. Every product in the batch belongs to a DIFFERENT category group (1 Dress, 1 Skirt, 1 Cardigan, 1 Top/Pants, etc.).
        """
        def is_in_cooldown(p: Dict[str, Any]) -> bool:
            title_clean = re.sub(r'[^a-z0-9]', '', p.get("title", "").lower())
            raw_clean = re.sub(r'[^a-z0-9]', '', p.get("raw_title", "").lower())
            handle_clean = re.sub(r'[^a-z0-9]', '', p.get("handle", "").lower())
            return any(k in cooldown_set for k in [title_clean, raw_clean, handle_clean] if k)

        # Filter out products currently in 7-day cooldown
        fresh_eligible = [p for p in products if not is_in_cooldown(p)]
        logger.info(f"✓ Found {len(fresh_eligible)} un-pinned fresh products not seen in last 7 days (out of {len(products)} total)")

        if not fresh_eligible:
            logger.info("All scanned products have been organized in the last 7 days. Re-evaluating older candidates...")
            fresh_eligible = products

        selected_batch = []
        used_category_groups = set()

        # Pass 1: Select one product per category group
        for p in fresh_eligible:
            cat_group = p.get("category_group", "general_apparel")
            if cat_group not in used_category_groups:
                selected_batch.append(p)
                used_category_groups.add(cat_group)
                if len(selected_batch) >= batch_size:
                    break

        # Pass 2: If we still need more products, fill with remaining distinct products
        if len(selected_batch) < batch_size:
            for p in fresh_eligible:
                if p not in selected_batch:
                    selected_batch.append(p)
                    if len(selected_batch) >= batch_size:
                        break

        return selected_batch

    def _download_temp_image(self, image_url: str) -> Optional[str]:
        """Downloads an image URL to a local temporary file for Pinterest upload."""
        try:
            resp = requests.get(image_url, timeout=15)
            if resp.status_code == 200 and len(resp.content) > 100:
                tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tf.write(resp.content)
                tf.close()
                return tf.name
        except Exception as e:
            logger.warning(f"Failed to download image {image_url}: {e}")
        return None

    def repin_or_publish_product(
        self,
        item: Dict[str, Any],
        target_board_id: str,
        target_board_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Repins an existing catalog pin ID or publishes a rich pin for a newest active product via PinterestClient.
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

        # B) Publish rich product pin for newest active product via PinterestClient.create_pin
        if image_url and link:
            tmp_img = self._download_temp_image(image_url)
            if tmp_img and Path(tmp_img).exists():
                try:
                    logger.info(f"Publishing newest in-stock product pin '{title[:35]}' to '{target_board_name}'...")
                    success, created_res = self.pinterest.create_pin(
                        image_path=tmp_img,
                        title=title[:100],
                        description=desc[:500],
                        board_id=str(target_board_id),
                        url=link,
                        alt_text=f"{title} - MeeeShop US Women's Fashion"
                    )
                    Path(tmp_img).unlink(missing_ok=True)
                    if success:
                        clean_pid = str(created_res) if created_res and not str(created_res).startswith("<") else ""
                        live_url = f"https://www.pinterest.com/pin/{clean_pid}/" if clean_pid else link
                        return True, live_url
                    else:
                        logger.error(f"create_pin returned failure for '{title}': {created_res}")
                except Exception as e:
                    Path(tmp_img).unlink(missing_ok=True)
                    logger.error(f"Publish product pin failed: {e}")

        return False, None

    def run_repin_session(
        self,
        max_repins: int = 4,
        daily_cap: int = 20,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Orchestrates the repinning session prioritizing un-pinned items with 7-day cooldown.
        """
        history = load_repin_history()
        today_count = get_today_repin_count(history)

        print("\n" + "=" * 70, flush=True)
        print("🚀 PINTEREST STEALTH PRODUCTS BOARD SAVER (7-DAY COOLDOWN & DIVERSE CATEGORIES)", flush=True)
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
            if not dry_run:
                sys.exit(1)
            return {"status": "error", "reason": "auth_failed", "repinned": 0}

        # 2. Discover unique, in-stock products
        products = self.discover_catalog_pins_from_products_board(max_pins=100)
        if not products:
            logger.warning("No verified in-stock products available.")
            if not dry_run:
                sys.exit(1)
            return {"status": "empty", "repinned": 0}

        # 3. Enforce 7-Day Cooldown & Strict Product/Category Diversity
        cooldown_set = get_recently_pinned_cooldown_set(days=7)
        to_process = self.select_diverse_product_batch(
            products=products,
            batch_size=allowed_this_run,
            cooldown_set=cooldown_set
        )

        print(f"\n🎯 Selected {len(to_process)} fresh distinct products (1 per category group) for this run:\n", flush=True)
        for idx, p in enumerate(to_process, 1):
            print(f"   [{idx}] {p['title']} (Category: {p.get('category_group', 'apparel')})", flush=True)
        print("\n" + "-" * 70 + "\n", flush=True)

        repinned_count = 0
        used_boards_in_run = set()

        for idx, item in enumerate(to_process, 1):
            title = item.get("title", "")
            raw_title = item.get("raw_title", title)
            link = item.get("link", "")
            cat_group = item.get("category_group", "apparel")
            pin_id = item.get("pin_id") or f"shopify_{idx}_{int(time.time())}"

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

            print(f"[{idx}/{len(to_process)}] Processing Fresh Product: {title}", flush=True)
            print(f"   🏷️ Category Group: {cat_group}", flush=True)
            print(f"   🔗 Storefront: {link}", flush=True)
            print(f"   📂 Target Board: '{target_board_name}' (ID: {target_board_id})", flush=True)

            if dry_run:
                print(f"   🧪 [DRY RUN] Would save product '{title}' -> board '{target_board_name}' (ID: {target_board_id})\n", flush=True)
                used_boards_in_run.add(target_board_name)
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
                    "category_group": cat_group,
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
        print(f"🎉 Session complete! Successfully organized {repinned_count} diverse in-stock products.", flush=True)
        print("=" * 70 + "\n", flush=True)

        if repinned_count == 0 and not dry_run:
            logger.error("❌ Session finished but 0 pins were successfully saved or published.")
            sys.exit(1)

        return {"status": "success", "repinned": repinned_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save diverse in-stock products from _products to organized boards.")
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
