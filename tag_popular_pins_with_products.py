#!/usr/bin/env python3
"""
tag_popular_pins_with_products.py — Auto-Tag Shoppable Products onto Popular Pinterest Pins

Features & Options:
1. Single Pin Test Mode (`--test-pin-id 962222276632068955`):
   Test product matching, tag payload, and API execution on a single Pin before full automation.
2. Dry-Run Mode (`--dry-run` vs `--apply`):
   Preview the exact matched product, price, and tag payload without making live changes.
3. Original Pin Link Preserved:
   The Pin's original destination URL and redirection link stay 100% UNCHANGED / INTACT.
4. Rule 1: If original pin link is IN-STOCK -> IGNORE.
   If original link is OUT-OF-STOCK / 404 -> Tag SIMILAR IN-STOCK PRODUCT on Pin image.
5. Rule 2 (7-Day Re-Verification): Re-check tagged products every 7 days. If a tagged product goes out of stock,
   replace the tagged product with a fresh, similar in-stock product.

Supports CLI testing, manual debugging, and GitHub Actions automated workflows.
"""

import os
import sys
import time
import json
import re
import random
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
import requests

# ── Paths & Environment Setup ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TagPopularPins")

# Secrets Manager integration
try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
    logger.info("[secrets] Double-encryption secrets injected successfully.")
except Exception as e:
    logger.warning(f"[secrets] secrets_manager fallback: {e}")
    def get_secret(key: str) -> Optional[str]:
        return os.environ.get(key)

# Pinterest Client integration
try:
    from pinterest_client import PinterestClient
except Exception as e:
    logger.warning(f"[PinterestClient] Import notice: {e}")
    PinterestClient = None

HISTORY_FILE = ROOT / "tagged_popular_pins_history.json"


def safe_get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        val = get_secret(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


# ── Step 1: Fetch In-Stock Active Products from Shopify ───────────────────────

def fetch_instock_shopify_products() -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Fetch active in-stock products from Shopify Admin API."""
    store = safe_get_secret("SHOPIFY_STORE", "us-meeeshop.myshopify.com")
    token = safe_get_secret("SHOPIFY_ACCESS_TOKEN", "")
    
    if not token:
        logger.error("Missing SHOPIFY_ACCESS_TOKEN! Cannot fetch products.")
        return [], set()

    url = f"https://{store}/admin/api/2024-10/products.json?status=active&limit=250"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    try:
        logger.info(f"Connecting to Shopify store ({store}) to fetch active in-stock catalog...")
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Shopify API returned status {resp.status_code}")
            return [], set()

        products = resp.json().get("products", [])
        valid_products = []
        instock_handles = set()

        for p in products:
            handle = p.get("handle")
            title = p.get("title")
            variants = p.get("variants", [])
            images = p.get("images", [])

            if not handle or not title or not variants:
                continue

            first_variant = variants[0]
            price = float(first_variant.get("price", 0))
            inv_qty = first_variant.get("inventory_quantity", 0)

            is_available = inv_qty > 0 or first_variant.get("inventory_policy") == "continue"
            if not is_available:
                continue

            instock_handles.add(handle)
            img_url = images[0].get("src") if images else ""

            valid_products.append({
                "id": str(p.get("id")),
                "variant_id": str(first_variant.get("id")),
                "handle": handle,
                "title": title,
                "price": price,
                "vendor": p.get("vendor", ""),
                "product_type": p.get("product_type", ""),
                "tags": p.get("tags", ""),
                "url": f"https://us.meeeshop.com/products/{handle}?utm_source=pinterest&utm_medium=shoppable_pin_tag&utm_campaign=popular_pin",
                "image_url": img_url,
                "keywords": extract_product_keywords(title, p.get("product_type", ""), p.get("tags", ""))
            })

        logger.info(f"Successfully retrieved {len(valid_products)} in-stock products from Shopify.")
        return valid_products, instock_handles

    except Exception as e:
        logger.error(f"Error fetching Shopify products: {e}")
        return [], set()


def extract_product_keywords(title: str, ptype: str, tags: str) -> List[str]:
    text = f"{title} {ptype} {tags}".lower()
    words = re.findall(r'\b[a-z]{3,}\b', text)
    stopwords = {"and", "the", "for", "with", "this", "that", "made", "usa", "size", "color", "new", "top", "set"}
    return list(set([w for w in words if w not in stopwords]))


def is_product_url_in_stock(url: str, instock_handles: Set[str]) -> bool:
    """Check if a product URL is currently in-stock."""
    if not url or "/products/" not in url:
        return False

    match = re.search(r'/products/([a-zA-Z0-9\-_]+)', url)
    if not match:
        return False

    handle = match.group(1).split('?')[0]
    if handle in instock_handles:
        return True

    try:
        js_url = f"https://us.meeeshop.com/products/{handle}.js"
        resp = requests.get(js_url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            return data.get("available", False)
    except Exception:
        pass
    return False


# ── Step 2: Product Matching Engine ───────────────────────────────────────────

def find_best_matching_product(pin_title: str, pin_desc: str, board_name: str, products: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Match a popular Pin's title & context against available in-stock products."""
    search_text = f"{pin_title} {pin_desc} {board_name}".lower()
    
    scored_products = []
    for prod in products:
        score = 0
        p_title = prod["title"].lower()
        p_type = prod["product_type"].lower()

        for word in search_text.split():
            if len(word) > 3 and word in p_title:
                score += 3
            elif len(word) > 3 and word in p_type:
                score += 2

        category_mappings = {
            "dress": ["dress", "midi", "maxi", "mini", "gown"],
            "bag": ["bag", "tote", "handbag", "shoulder", "purse"],
            "jeans": ["jeans", "denim", "jorts", "pants"],
            "sweater": ["sweater", "cardigan", "knit", "pullover"],
            "skirt": ["skirt", "midi skirt", "woven"],
            "top": ["shirt", "top", "blouse", "tee", "tank"]
        }

        for cat, keywords in category_mappings.items():
            if any(k in search_text for k in keywords):
                if any(k in p_title or k in p_type for k in keywords):
                    score += 5

        if score > 0:
            scored_products.append((score, prod))

    if not scored_products:
        return random.choice(products) if products else None

    scored_products.sort(key=lambda x: x[0], reverse=True)
    return scored_products[0][1]


# ── Step 3: History & Persistence ─────────────────────────────────────────────

def load_tagged_history() -> Dict[str, Any]:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"tagged_pins": {}, "last_run": None}


def save_tagged_history(history: Dict[str, Any]) -> None:
    history["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


# ── Step 4: Attach Relevant Tagged Products via Shopify Catalog Variant IDs ────

def find_relevant_shopify_products_for_pin(
    pin_title: str,
    pin_desc: str,
    board_name: str,
    pin_link: str,
    products: List[Dict[str, Any]],
    target_count: int = 10
) -> List[Dict[str, Any]]:
    """
    Finds up to 10 highly relevant, unique in-stock Shopify products for a specific Pin.
    Intelligently categorizes the Pin context into specific niches:
    - footwear / shoes / sandals / slippers
    - dresses / gowns / rompers / jumpsuits
    - shorts / activewear / workout / gym
    - sweaters / cardigans / knits / outerwear / pullovers
    - jeans / denim / pants / trousers / bottoms
    - tops / blouses / shirts / tees / tanks
    - bags / handbags / totes / purses / backpacks
    """
    combined_pin_text = f"{pin_link} {pin_title} {pin_desc} {board_name}".lower()

    category_definitions = {
        "footwear": {
            "triggers": ["shoe", "footwear", "boot", "sneaker", "heel", "sandal", "slipper", "loafer", "flat", "slides"],
            "product_keywords": ["slipper", "shoe", "boot", "sandal", "footwear", "sneaker", "flat", "heel", "jogger", "pants"]
        },
        "dress": {
            "triggers": ["dress", "maxi", "midi", "mini", "gown", "sundress", "romper", "jumpsuit", "bodycon"],
            "product_keywords": ["dress", "gown", "romper", "jumpsuit", "maxi", "midi", "tunic"]
        },
        "shorts_activewear": {
            "triggers": ["short", "biker", "drawstring", "activewear", "workout", "gym", "athletic", "running"],
            "product_keywords": ["short", "active", "legging", "jogger", "bra", "tank", "tee", "pant", "bottom"]
        },
        "sweater_knit": {
            "triggers": ["sweater", "cardigan", "knit", "pullover", "poncho", "turtleneck", "hoodie", "sweatshirt"],
            "product_keywords": ["sweater", "cardigan", "knit", "pullover", "poncho", "sweatshirt", "jacket"]
        },
        "denim_pants": {
            "triggers": ["jean", "denim", "pant", "trouser", "bottom", "cargo", "flare", "wide leg"],
            "product_keywords": ["denim", "jean", "pant", "trouser", "bottom", "legging"]
        },
        "bags_accessories": {
            "triggers": ["bag", "tote", "handbag", "purse", "shoulder", "crossbody", "clutch", "backpack", "wallet"],
            "product_keywords": ["handbag", "bag", "tote", "backpack", "pouch", "clutch", "purse", "accessories"]
        },
        "tops_blouses": {
            "triggers": ["top", "shirt", "blouse", "tee", "t-shirt", "tank", "camisole", "crop", "tunic"],
            "product_keywords": ["top", "shirt", "blouse", "tee", "tank", "tunic", "camisole"]
        }
    }

    matched_categories = []
    for cat_name, cat_data in category_definitions.items():
        if any(trig in combined_pin_text for trig in cat_data["triggers"]):
            matched_categories.append(cat_name)

    if not matched_categories:
        matched_categories = ["tops_blouses", "dress"]

    scored_products = []
    seen_ids = set()

    for p in products:
        p_id = p.get("id")
        if p_id in seen_ids:
            continue

        p_text = f"{p.get('title', '')} {p.get('product_type', '')} {p.get('tags', '')}".lower()
        score = 0

        # High weight for matching targeted niche category
        for cat_name in matched_categories:
            cat_keywords = category_definitions[cat_name]["product_keywords"]
            for kw in cat_keywords:
                if kw in p_text:
                    score += 15

        # Word overlaps from pin title, description, and URL handle
        for word in combined_pin_text.split():
            clean_word = re.sub(r'[^a-z]', '', word)
            if len(clean_word) > 3 and clean_word in p_text:
                score += 3

        if score > 0:
            scored_products.append((score, p))
            seen_ids.add(p_id)

    # Sort descending by relevance score
    scored_products.sort(key=lambda x: x[0], reverse=True)
    selected = [p for _, p in scored_products[:target_count]]

    # If fewer than target_count, fill with remaining in-stock items
    if len(selected) < target_count:
        for p in products:
            if len(selected) >= target_count:
                break
            if p.get("id") not in seen_ids:
                selected.append(p)
                seen_ids.add(p.get("id"))

    return selected


def tag_pin_visually_with_playwright(
    pin_id: str,
    relevant_products: List[Dict[str, Any]],
    max_tags: int = 10
) -> bool:
    """
    Automates visual product tagging directly via the Pinterest 'Catalog' tab:
    1. Loads https://www.pinterest.com/pin/{pin_id}/
    2. Hovers image and clicks 'Tag products' (shopping bag icon)
    3. Clicks '+' in tagged-items-grid
    4. Clicks the 'Catalog' tab
    5. For each relevant Shopify product, inputs its exact Shopify variant_id to fetch the synced product card
    6. Clicks the product card to add it to the Pin (up to 10 products)
    7. Clicks 'Save products'
    8. Clicks 'Done' button to save tags live on the Pin!
    """
    try:
        from stealth_pinterest_poster import StealthPinterestPoster
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        logger.warning(f"  [Playwright] Playwright or StealthPinterestPoster not installed: {e}")
        return False

    try:
        poster = StealthPinterestPoster(headless=True)
        cookies = poster._get_cookies_dict()
        if not cookies:
            logger.warning("  [Playwright] No Pinterest cookies found for visual tagging.")
            return False

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage']
            )
            ctx = browser.new_context(viewport={'width': 1280, 'height': 900})
            ctx.add_cookies(cookies)
            page = ctx.new_page()

            logger.info(f"  [Playwright] 1. Loading Pin page: https://www.pinterest.com/pin/{pin_id}/")
            page.goto(f'https://www.pinterest.com/pin/{pin_id}/', wait_until='domcontentloaded')
            page.wait_for_timeout(3000)

            # Step 2: Hover over image and click "Tag products"
            logger.info("  [Playwright] 2. Hovering pin image to reveal 'Tag products' button...")
            img = page.locator("img").first
            if img.count() > 0:
                img.hover()
                page.wait_for_timeout(1000)

            tag_btn = page.locator("button[aria-label='Tag products']").first
            if tag_btn.count() == 0:
                logger.warning("  [Playwright] 'Tag products' button not found on Pin image.")
                browser.close()
                return False

            tag_btn.click()
            page.wait_for_timeout(3000)

            # Step 3: Click '+' in tagged-items-grid
            logger.info("  [Playwright] 3. Clicking '+' in tagged-items-grid...")
            grid = page.locator("[data-test-id='tagged-items-grid']")
            add_btn = grid.locator("div[role='button'], button, div[tabindex='0']").first
            if add_btn.count() == 0:
                logger.warning("  [Playwright] '+' button not found in tagged-items-grid.")
                browser.close()
                return False

            add_btn.click()
            page.wait_for_timeout(3000)

            dialog = page.locator('[role="dialog"]')

            # Step 4: Navigate to 'Catalog' tab
            logger.info("  [Playwright] 4. Switching to 'Catalog' tab for exact variant ID lookup...")
            catalog_tab = dialog.locator('button:has-text("Catalog"), div:has-text("Catalog")').last
            if catalog_tab.count() == 0:
                logger.warning("  [Playwright] 'Catalog' tab not found in modal.")
                browser.close()
                return False

            catalog_tab.click()
            page.wait_for_timeout(2000)

            inp = dialog.locator('input[placeholder*="Enter product item ID"]').first
            if inp.count() == 0:
                logger.warning("  [Playwright] 'Enter product item ID' input field not found.")
                browser.close()
                return False

            # Step 5: For each relevant product, enter variant_id and click the card
            logger.info(f"  [Playwright] 5. Tagging up to {max_tags} relevant Shopify products via variant IDs...")
            added_count = 0

            for i, prod in enumerate(relevant_products[:max_tags]):
                vid = str(prod.get('variant_id', '')).strip()
                if not vid:
                    continue

                safe_title = prod.get('title', '').encode('ascii', 'ignore').decode()[:35]
                logger.info(f"    Adding product #{added_count+1}: '{safe_title}' (variant ID: {vid})...")

                inp.fill(vid)
                inp.press("Enter")
                page.wait_for_timeout(2200)

                # Find the matched catalog card
                card = dialog.locator('img[src*="pinimg"]').last
                if card.count() > 0:
                    try:
                        card.click()
                        added_count += 1
                        logger.info(f"      Successfully added product #{added_count}")
                        page.wait_for_timeout(600)
                    except Exception as e:
                        logger.debug(f"Click card notice: {e}")
                else:
                    logger.warning(f"      Product card not found for variant ID {vid}")

            if added_count == 0:
                logger.warning("  [Playwright] 0 products were added via Catalog variant IDs.")
                browser.close()
                return False

            logger.info(f"  [Playwright] Successfully added {added_count} relevant products from Catalog.")

            # Step 6: Click "Save products" / "Save product"
            logger.info("  [Playwright] 6. Clicking 'Save products'...")
            save_btn = page.locator("button:has-text('Save products')").first
            if save_btn.count() == 0:
                save_btn = page.locator("button:has-text('Save product')").first

            if save_btn.count() > 0 and save_btn.is_enabled():
                save_btn.click()
                page.wait_for_timeout(3000)

            # Step 7: Click "Done" button to save tags on Pin
            logger.info("  [Playwright] 7. Clicking 'Done' button to save tags on Pin...")
            done_btn = page.locator("button:has-text('Done')").first
            if done_btn.count() > 0:
                done_btn.click()
                page.wait_for_timeout(4000)
                logger.info(f"  [SUCCESS] [Playwright] Successfully tagged {added_count} relevant products onto Pin #{pin_id} (title, desc & URL 100% untouched)!")
                browser.close()
                return True
            else:
                logger.warning("  [Playwright] 'Done' button not found.")
                browser.close()
                return False

    except Exception as e:
        logger.error(f"  [Playwright] Visual tagging exception: {e}")
        return False


def attach_tagged_product_to_pin(
    pclient: Any,
    pin_id: str,
    orig_link: str,
    relevant_products: List[Dict[str, Any]],
    pin_title: str = "",
    pin_desc: str = "",
    apply_live: bool = False
) -> bool:
    """
    Attaches up to 10 relevant Shoppable Products to the Pin image via Catalog variant IDs.
    IMPORTANT:
    1. Does NOT edit the Pin title, description, or URL. All remain 100% UNTOUCHED!
    2. Tags up to 10 relevant in-stock products visually via Catalog variant IDs.
    """
    first_prod = relevant_products[0] if relevant_products else {}
    logger.info(f"\n[TAGGING RELEVANT SHOPIFY PRODUCTS FOR PIN #{pin_id}]")
    logger.info(f"  Original Redirection URL (100% UNTOUCHED) : {orig_link or 'https://us.meeeshop.com'}")
    logger.info(f"  Pin Title & Description (100% UNTOUCHED)  : Preserved intact")
    logger.info(f"  Total Relevant In-Stock Products Found   : {len(relevant_products)}")
    for idx, p in enumerate(relevant_products[:5]):
        logger.info(f"    Item #{idx+1}: {p.get('title')} (${p.get('price')}) | Variant ID: {p.get('variant_id')}")

    if apply_live:
        visual_success = tag_pin_visually_with_playwright(pin_id, relevant_products, max_tags=10)
        return visual_success
    else:
        logger.info("  [TEST / DRY-RUN MODE] Visual tagging simulated for up to 10 products (No live edit made).")

    return True


# ── Step 5: Core Automation & Test Execution Pipeline ─────────────────────────

def process_and_tag_popular_pins(
    max_pins: int = 10,
    test_pin_id: Optional[str] = None,
    apply_live: bool = False
) -> Dict[str, Any]:
    """
    Core Execution & Test Pipeline:
    - If `test_pin_id` is provided, tests product matching & tagging on that SINGLE Pin.
    - If `apply_live` is True, executes live update; otherwise runs in Dry-Run/Audit mode.
    """
    mode_str = "LIVE API UPDATE MODE (--apply)" if apply_live else "PREVIEW / TEST MODE (--dry-run)"
    logger.info(f"\n=================================================================")
    logger.info(f"  RUNNING TAG POPULAR PINS IN: {mode_str}")
    if test_pin_id:
        logger.info(f"  SINGLE PIN TEST TARGET: {test_pin_id}")
    logger.info(f"=================================================================")

    products, instock_handles = fetch_instock_shopify_products()
    if not products:
        logger.error("No valid in-stock products found. Exiting.")
        return {"status": "error", "message": "No products available"}

    history = load_tagged_history()
    tagged_map = history.get("tagged_pins", {})

    logger.info("Initializing Pinterest API Client...")
    pclient = None
    if PinterestClient:
        try:
            pclient = PinterestClient()
            if not pclient.login():
                logger.warning("PinterestClient login notice. Proceeding with fallback mode.")
                pclient = None
        except Exception as e:
            logger.warning(f"PinterestClient init exception: {e}")
            pclient = None

    # ── TEST SINGLE PIN MODE ──────────────────────────────────────────────────
    if test_pin_id:
        logger.info(f"\n--- TESTING SINGLE PIN: ID #{test_pin_id} ---")
        pin_context = {
            "id": test_pin_id,
            "title": "MeeeShop: Shop Dresses, Jeans, Clothes, Shoes, & Accessories For Women",
            "desc": "Shop high quality women's fashion, tote bags, shapewear dresses, and jeans.",
            "board_name": "My Shop",
            "link": f"https://www.pinterest.com/pin/{test_pin_id}/"
        }

        # Attempt to fetch exact pin details if client active
        if pclient and hasattr(pclient, 'client') and pclient.client:
            try:
                options = {"id": str(test_pin_id)}
                url = pclient.client.req_builder.buildGet(
                    url="https://www.pinterest.com/resource/PinResource/get/",
                    options=options,
                    source_url=f"/pin/{test_pin_id}/"
                )
                p_resp = pclient.client.get(url=url).json()
                p_data = p_resp.get("resource_response", {}).get("data", {})
                if p_data:
                    pin_context["title"] = str(p_data.get('title') or p_data.get('grid_title') or pin_context["title"])
                    pin_context["desc"] = str(p_data.get('description') or pin_context["desc"])
                    pin_context["link"] = str(p_data.get('link') or pin_context["link"])
                    logger.info(f"Retrieved exact live details for Pin #{test_pin_id}: title='{pin_context['title']}', link='{pin_context['link']}'")
            except Exception as ex:
                logger.debug(f"Fetch exact pin details notice: {ex}")

        relevant_prods = find_relevant_shopify_products_for_pin(
            pin_context["title"],
            pin_context["desc"],
            pin_context["board_name"],
            pin_context["link"],
            products,
            target_count=10
        )
        if not relevant_prods:
            logger.error("Could not find matching products for test pin.")
            return {"status": "error", "message": "No match found"}

        first_prod = relevant_prods[0]

        success = attach_tagged_product_to_pin(
            pclient,
            test_pin_id,
            pin_context["link"],
            relevant_prods,
            pin_title=pin_context["title"],
            pin_desc=pin_context["desc"],
            apply_live=apply_live
        )

        test_result = {
            "pin_id": test_pin_id,
            "original_link": pin_context["link"],
            "primary_matched_product": first_prod["title"],
            "tagged_products_count": len(relevant_prods),
            "tagged_products": [
                {"title": p["title"], "price": p["price"], "variant_id": p.get("variant_id"), "url": p["url"]}
                for p in relevant_prods
            ],
            "live_applied": success if apply_live else False,
            "mode": mode_str
        }

        if apply_live and success:
            record = {
                "pin_id": test_pin_id,
                "pin_title": pin_context["title"],
                "original_link": pin_context["link"],
                "tagged_products": [
                    {
                        "id": p["id"],
                        "variant_id": p.get("variant_id"),
                        "handle": p["handle"],
                        "title": p["title"],
                        "price": p["price"],
                        "url": p["url"],
                        "image_url": p["image_url"]
                    }
                    for p in relevant_prods
                ],
                "tagged_at": datetime.now(timezone.utc).isoformat(),
                "verified_at": datetime.now(timezone.utc).isoformat()
            }
            tagged_map[test_pin_id] = record
            history["tagged_pins"] = tagged_map
            save_tagged_history(history)
            logger.info(f"[SUCCESS] Saved Pin #{test_pin_id} with {len(relevant_prods)} tagged products to history!")

        logger.info(f"\n--- SINGLE PIN TEST COMPLETE ---")
        logger.info(json.dumps(test_result, indent=2))
        return test_result

    # ── FULL BATCH PIPELINE ───────────────────────────────────────────────────
    # 7-Day Re-Verification of History Entries
    logger.info("\n--- 7-DAY RE-VERIFICATION OF TAGGED PRODUCTS ---")
    reverified_count = 0
    replaced_count = 0

    for pid, rec in list(tagged_map.items()):
        tagged_prod_url = rec.get("tagged_product", {}).get("url") or rec.get("target_url", "")
        tagged_prod_title = rec.get("tagged_product", {}).get("title") or rec.get("product_title", "Item")
        orig_pin_link = rec.get("original_link") or "https://us.meeeshop.com"

        still_in_stock = is_product_url_in_stock(tagged_prod_url, instock_handles)
        if not still_in_stock:
            logger.info(f"⚠️ Tagged product '{tagged_prod_title}' on Pin #{pid} is now OUT-OF-STOCK!")
            logger.info("   Searching for similar in-stock replacement item...")
            replacement = find_best_matching_product(str(rec.get("pin_title") or ""), "", "", products)
            if replacement:
                attach_tagged_product_to_pin(
                    pclient,
                    pid,
                    orig_pin_link,
                    replacement,
                    pin_title=str(rec.get("pin_title") or ""),
                    apply_live=apply_live
                )
                
                rec["tagged_product"] = {
                    "id": replacement["id"],
                    "handle": replacement["handle"],
                    "title": replacement["title"],
                    "price": replacement["price"],
                    "url": replacement["url"],
                    "image_url": replacement["image_url"]
                }
                rec["replaced_at"] = datetime.now(timezone.utc).isoformat()
                rec["verified_at"] = datetime.now(timezone.utc).isoformat()
                replaced_count += 1
                logger.info(f"  [SUCCESS] Tagged product REPLACED with: '{replacement['title']}' (${replacement['price']})")
        else:
            rec["verified_at"] = datetime.now(timezone.utc).isoformat()
            reverified_count += 1

    logger.info(f"Re-verification complete: {reverified_count} Tagged Products verified IN-STOCK, {replaced_count} REPLACED out-of-stock products.\n")

    # Discover & Tag Popular Pins
    target_pin_ids = ["962222276632068955"]
    discovered_pins = []

    if pclient and hasattr(pclient, 'fetch_boards'):
        try:
            boards = pclient.fetch_boards() or []
            logger.info(f"Found {len(boards)} Pinterest boards on account.")
            for b in boards[:10]:
                bid = b.get('id')
                bname = b.get('name', 'General')
                if not bid:
                    continue
                try:
                    bpins = pclient.client.board_feed(board_id=bid, page_size=15)
                    for pin in (bpins or []):
                        pid = str(pin.get('id', ''))
                        if pid and pid not in target_pin_ids:
                            discovered_pins.append({
                                "id": pid,
                                "title": str(pin.get('title') or pin.get('grid_title') or bname),
                                "desc": str(pin.get('description') or ''),
                                "board_name": bname,
                                "link": str(pin.get('link') or 'https://us.meeeshop.com'),
                                "save_count": pin.get('save_count', 0) or pin.get('repin_count', 0) or 0
                            })
                except Exception as ex:
                    logger.debug(f"Error fetching board {bname}: {ex}")
        except Exception as e:
            logger.warning(f"Error iterating boards: {e}")

    for t_id in target_pin_ids:
        if not any(p['id'] == t_id for p in discovered_pins):
            discovered_pins.insert(0, {
                "id": t_id,
                "title": "MeeeShop: Shop Dresses, Jeans, Clothes, Shoes, & Accessories For Women",
                "desc": "Shop high quality women's clothing, slouchy tote bags, shapewear dresses, and jeans.",
                "board_name": "My Shop",
                "link": "https://www.pinterest.com/pin/962222276632068955/",
                "save_count": 999
            })

    discovered_pins.sort(key=lambda x: x.get("save_count", 0), reverse=True)
    logger.info(f"Total candidate popular Pins ready for evaluation: {len(discovered_pins)}")

    results = []
    count = 0

    for pin in discovered_pins:
        if count >= max_pins:
            break

        pin_id = str(pin.get("id") or "")
        if not pin_id:
            continue

        if pin_id in tagged_map:
            continue

        pin_title_str = str(pin.get("title") or "")
        pin_desc_str = str(pin.get("desc") or "")
        pin_board_str = str(pin.get("board_name") or "")
        orig_link = str(pin.get("link") or "https://us.meeeshop.com")

        if orig_link and "/products/" in orig_link:
            if is_product_url_in_stock(orig_link, instock_handles):
                logger.info(f"Pin #{pin_id} original item '{orig_link}' is ALREADY IN-STOCK. Ignoring pin (leaving intact).")
                continue
            else:
                logger.info(f"Pin #{pin_id} original item '{orig_link}' is OUT-OF-STOCK or 404! Tagging similar in-stock product.")

        relevant_prods = find_relevant_shopify_products_for_pin(
            pin_title_str,
            pin_desc_str,
            pin_board_str,
            orig_link,
            products,
            target_count=10
        )
        if not relevant_prods:
            continue

        first_prod = relevant_prods[0]

        success = attach_tagged_product_to_pin(
            pclient,
            pin_id,
            orig_link,
            relevant_prods,
            pin_title=pin_title_str,
            pin_desc=pin_desc_str,
            apply_live=apply_live
        )

        if success:
            record = {
                "pin_id": pin_id,
                "pin_title": pin_title_str,
                "original_link": orig_link,
                "tagged_products": [
                    {
                        "id": p["id"],
                        "variant_id": p.get("variant_id"),
                        "handle": p["handle"],
                        "title": p["title"],
                        "price": p["price"],
                        "url": p["url"],
                        "image_url": p["image_url"]
                    }
                    for p in relevant_prods
                ],
                "tagged_at": datetime.now(timezone.utc).isoformat(),
                "verified_at": datetime.now(timezone.utc).isoformat()
            }
            tagged_map[pin_id] = record
            results.append(record)
            count += 1
            time.sleep(random.uniform(1.5, 3.0))

    history["tagged_pins"] = tagged_map
    save_tagged_history(history)

    logger.info(f"\n=================================================================")
    logger.info(f"  Execution Complete: {len(results)} new Pins tagged with Shoppable products.")
    logger.info(f"  Original Pin URLs & Redirection Links: 100% PRESERVED INTACT.")
    logger.info(f"  History Total: {len(tagged_map)} Pins tracked and verified.")
    logger.info(f"  History File : {HISTORY_FILE.name}")
    logger.info(f"=================================================================")

    return {
        "status": "success",
        "tagged_count": len(results),
        "reverified_count": reverified_count,
        "replaced_count": replaced_count,
        "tagged_items": results
    }


def main():
    parser = argparse.ArgumentParser(description="Tag popular saved Pinterest Pins with similar in-stock Shopify products.")
    parser.add_argument("--test-pin-id", type=str, default=None, help="Test product matching & tag payload on a SINGLE Pinterest Pin ID (e.g. 962222276632068955).")
    parser.add_argument("--apply", action="store_true", default=False, help="Execute live product tag updates on Pinterest API.")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Preview product matching without modifying Pinterest.")
    parser.add_argument("--max-pins", type=int, default=5, help="Maximum number of popular pins to tag per batch run.")
    args = parser.parse_args()

    # If --apply is specified without --dry-run, execute live API updates
    apply_live = bool(args.apply and not args.dry_run)

    res = process_and_tag_popular_pins(
        max_pins=args.max_pins,
        test_pin_id=args.test_pin_id,
        apply_live=apply_live
    )

    if apply_live:
        if args.test_pin_id:
            if not res or not res.get("live_applied", False):
                logger.error(f"[FAILURE] Live tagging failed for test Pin #{args.test_pin_id}.")
                sys.exit(1)
        else:
            if not res or res.get("status") == "error":
                logger.error("[FAILURE] Live tagging encountered an error.")
                sys.exit(1)


if __name__ == "__main__":
    main()
