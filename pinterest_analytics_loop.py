#!/usr/bin/env python3
"""
pinterest_analytics_loop.py — Evergreen Traffic & OOS Hijack Loop
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Uses py3-pinterest API to fetch your boards and recent pins natively.
2. Evaluates each pin's API engagement stats (Saves) and extracts the Shopify URL.
3. If highly engaged -> Checks Shopify inventory for that product handle.
4. IF IN STOCK: Re-pins to a new overlapping relevant board.
5. IF OUT OF STOCK: Creates a 301 redirect in Shopify & piggybacks the replacement pin.
"""

import os
import sys
import time
import json
import random
import re
import argparse
from pathlib import Path
import traceback # Added for detailed error logging
import requests
import tempfile
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# ── Local Imports ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pinterest_client import PinterestClient
from shopify_products import get_pinterest_board_mapping
import content_generator

# ── Secrets Management ────────────────────────────────────────────────────────
# Utilizing existing double-encryption secrets manager
try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
except ImportError:
    print("[WARN] secrets_manager not found. Falling back to os.environ.")
    def get_secret(key): return os.environ.get(key)

SHOPIFY_STORE = get_secret("SHOPIFY_STORE_URL")
SHOPIFY_TOKEN = get_secret("SHOPIFY_ACCESS_TOKEN")
PINTEREST_EMAIL = get_secret("PINTEREST_EMAIL")
PINTEREST_PASSWORD = get_secret("PINTEREST_PASSWORD")

API_VER = "2024-10"
HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Threshold for a pin to be considered "Viral" or highly engaged
VIRAL_SAVES_THRESHOLD = 3 

def parse_args():
    parser = argparse.ArgumentParser(description="Pinterest Analytics & Evergreen Loop")
    parser.add_argument("--batch-size", type=int, default=0, help="Number of pins to process per batch (0 = all)")
    parser.add_argument("--batch-index", type=int, default=0, help="Batch index to process")
    parser.add_argument("--limit", type=int, default=0, help="Max total pins to select before batching (0 = all)")
    parser.add_argument("--days", type=int, default=60, help="Number of days to look back for pins")
    return parser.parse_args()

# ── Shopify API Helpers ───────────────────────────────────────────────────────
def _shopify_get(endpoint, params=None):
    base = SHOPIFY_STORE.rstrip('/')
    url = f"{base}/admin/api/{API_VER}/{endpoint}"
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()

def _shopify_post(endpoint, payload):
    base = SHOPIFY_STORE.rstrip('/')
    url = f"{base}/admin/api/{API_VER}/{endpoint}"
    response = requests.post(url, headers=HEADERS, json=payload)
    if response.status_code not in (200, 201):
        print(f"[ERROR] Shopify POST failed: {response.text}")
    return response.json()

def get_product_by_handle(handle):
    """Fetch product details by handle to check stock."""
    data = _shopify_get("products.json", {"handle": handle, "status": "any"})
    products = data.get("products", [])
    if not products:
        return None
    return products[0]

def is_in_stock(product):
    """Check if any variant has inventory."""
    for v in product.get("variants", []):
        if v.get("inventory_policy") == "continue":
            return True
        qty = v.get("inventory_quantity", 0)
        if qty is None or qty > 0:
            return True
    return False

def find_in_stock_replacement(out_product, handle_hint=""):
    """Find the best in-stock alternative in the same product type."""
    ptype = out_product.get("product_type", "") if out_product else ""
    if not ptype and handle_hint:
        h = handle_hint.lower()
        if 'dress' in h: ptype = 'Dresses'
        elif 'top' in h or 'blouse' in h or 'shirt' in h: ptype = 'Tops'
        elif 'jeans' in h or 'denim' in h: ptype = 'Jeans'
        elif 'pants' in h or 'legging' in h: ptype = 'Pants & Leggings'
        elif 'sweater' in h or 'cardigan' in h: ptype = 'Sweaters'
        elif 'jacket' in h or 'coat' in h: ptype = 'Coats & Jackets'

    params = {"limit": 250, "status": "active"}
    if ptype:
        params["product_type"] = ptype
    data = _shopify_get("products.json", params)
    pool = [p for p in data.get("products", []) if is_in_stock(p) and (not out_product or p.get("id") != out_product.get("id"))]
    
    if pool:
        return random.choice(pool)
    if ptype:
        # Fallback to any product
        data = _shopify_get("products.json", {"limit": 250, "status": "active"})
        pool = [p for p in data.get("products", []) if is_in_stock(p) and (not out_product or p.get("id") != out_product.get("id"))]
        if pool:
            return random.choice(pool)
    return None

def create_shopify_redirect(old_handle, new_handle):
    """Create a 301 redirect for hijacked traffic."""
    payload = {
        "redirect": {
            "path": f"/products/{old_handle}",
            "target": f"/products/{new_handle}"
        }
    }
    print(f"    [Shopify] Creating 301 Redirect: {old_handle} -> {new_handle}")
    return _shopify_post("redirects.json", payload)

def extract_shopify_handle(text):
    """Extracts meeeshop handle from text/URLs."""
    match = re.search(r'meeeshop\.com/products/([a-z0-9\-]+)', str(text).lower())
    if match:
        return match.group(1)
    return None

def download_image_to_temp(url):
    """Download an image to a temporary file for Pinterest upload."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(resp.content)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"   [WARN] Failed to download image: {e}")
        return None

# ── Fallback Selenium Analytics Fetcher ───────────────────────────────────────
def get_top_performing_pins_analytics(client):
    """Fallback: Use Selenium to scrape Analytics dashboard for pins getting traffic right now."""
    print("   [Fallback] Using Selenium to scrape Analytics URL for viral pins...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get("https://www.pinterest.com/login/")
        time.sleep(2)
        
        session = client._get_raw_session()
        for cookie in session.cookies:
            driver.add_cookie({
                "name": cookie.name,
                "value": cookie.value,
                "domain": ".pinterest.com"
            })
            
        analytics_url = "https://analytics.pinterest.com/overview/?content_type=organic&aggregation=last30d&age=all&board_metric=IMPRESSION&board_id=&claimed_account_type=all&device_type=all&gender=all&include_curated=created&include_realtime=true&pin_format=all&pin_metric=ENGAGEMENT&primary_metric=IMPRESSION&recent_pins=false&selected_split=NO_SPLIT&source_type=all"
        
        print("   [Selenium] Navigating to Analytics dashboard...")
        driver.get(analytics_url)
        time.sleep(15) # Wait for heavy JS dashboard to load
        
        # Scroll to lazy load the table
        driver.execute_script("window.scrollBy(0, 1500);")
        time.sleep(5)
        
        pin_links = []
        elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/pin/')]")
        for el in elements:
            href = el.get_attribute("href")
            if href and "/pin/" in href and href not in pin_links:
                pin_links.append(href)
                
        print(f"   [Selenium] Found {len(pin_links)} top pins from Analytics table.")
        return pin_links[:20]
        
    except Exception as e:
        print(f"   [WARN] Analytics fallback failed: {e}")
        return []
    finally:
        driver.quit()

def get_pin_details_api(client, pin_url):
    """Fetch pin details securely using the authenticated session."""
    pin_id = pin_url.split('/pin/')[-1].strip('/')
    try:
        session = client._get_raw_session()
        url = "https://www.pinterest.com/resource/PinResource/get/"
        params = {"data": json.dumps({"options": {"id": pin_id, "field_set_key": "detailed"}})}
        headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
        
        resp = session.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("resource_response", {}).get("data", {})
    except Exception as e:
        print(f"   [WARN] Failed to fetch pin details for {pin_id}: {e}")
    return {}

# ── API Pin Fetcher ───────────────────────────────────────────────────────────
def get_top_performing_pins(client, limit=0, days=30):
    """Fetch recent pins natively via py3-pinterest and sort by actual saves."""
    print(f"   [API] Fetching pins from the last {days} days across boards...")
    boards = client.fetch_boards()
    
    recent_pins = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    total_scanned = 0
    total_skipped_date = 0
    total_skipped_api_error = 0 # Added to track API errors within loop
    total_skipped_handle = 0

    for board in boards:
        board_id = board.get('id')
        if not board_id:
            continue
            
        try:
            # Handle py3-pinterest bookmark quirks safely
            bookmarks = getattr(client.client, 'bookmarks', None)
            
            if isinstance(bookmarks, dict):
                bookmarks.pop(board_id, None) 

            page_count = 0
            while page_count < 3: # Fetch up to 75 pins per board
                try:
                    board_pins = client.client.board_feed(board_id=board_id, page_size=25, reset_bookmark=False)
                except KeyError:
                    if isinstance(bookmarks, dict):
                        print(f"       [DEBUG] KeyError on first board_feed for {board.get('name')}. Resetting bookmark and retrying.")
                        bookmarks[board_id] = ''
                    board_pins = client.client.board_feed(board_id=board_id, page_size=25, reset_bookmark=False)

                if not board_pins:
                    break

                for pin in board_pins:
                    total_scanned += 1
                    # Parse creation date
                    
                    # DEBUG: Print raw pin data for initial investigation
                    if total_scanned < 5: # Only print for first few pins to avoid excessive output
                        print(f"       [DEBUG] Raw pin data for {pin.get('id')}: {json.dumps(pin, indent=2)}")
                        
                    raw_ts = pin.get('created_at') or pin.get('created_time') or (pin.get('pin_join') or {}).get('created_at', '')
                        
                    is_too_old = False
                    if raw_ts:
                        try:
                            if "," in raw_ts:
                                from email.utils import parsedate_to_datetime
                                pin_date = parsedate_to_datetime(raw_ts).replace(tzinfo=None)
                            else:
                                pin_date = datetime.fromisoformat(raw_ts.replace("Z", "+00:00").split("+")[0])
                            
                            if pin_date < cutoff_date:
                                is_too_old = True
                        except Exception:
                            pass 
                    
                    if is_too_old:
                        total_skipped_date += 1
                        continue
                        
                    saves = int(pin.get('repin_count') or pin.get('save_count') or 0)
                    if saves == 0:
                        saves = int(pin.get('aggregated_pin_data', {}).get('saves') or 0)
                    if saves == 0:
                        saves = int(pin.get('pin_metrics', {}).get('saves') or 0)
                        
                    link = pin.get('link') or pin.get('url') or ''
                    handle = extract_shopify_handle(link)
                    if not handle:
                        handle = extract_shopify_handle(pin.get('description', ''))
                        
                    if not handle:
                        total_skipped_handle += 1
                        continue

                    recent_pins.append({
                        'pin_id': pin.get('id'),
                        'pin_url': f"https://www.pinterest.com/pin/{pin.get('id')}/",
                        'saves': saves,
                        'handle': handle,
                        'board_name': board.get('name')
                    })
                
                page_count += 1
                time.sleep(0.3)
                
        except Exception: # Catch broader exceptions during pin fetching
            total_skipped_api_error += 1
            print(f"   [ERROR] Failed to fetch pins for board {board.get('name')}. Full traceback:")
            traceback.print_exc() # Print full traceback for detailed debugging
            
    print(f"   [API] Scanned {total_scanned} total pins.")
    print(f"   [API] Skipped {total_skipped_date} due to age (>30 days).")
    print(f"   [API] Skipped {total_skipped_handle} due to missing Shopify link.")

    # Sort by saves descending
    recent_pins.sort(key=lambda x: x['saves'], reverse=True)
    print(f"   [API] Found {len(recent_pins)} eligible pins from the last {days} days.")
    
    # Deduplicate by handle, keeping the one with most saves
    seen_handles = set()
    deduped_pins = []
    for pin in recent_pins:
        if pin['handle'] not in seen_handles:
            seen_handles.add(pin['handle'])
            deduped_pins.append(pin)
            
    if limit and limit > 0:
        return deduped_pins[:limit]
    return deduped_pins

def get_new_board(original_board, product_data):
    """Find a new board mapping that wasn't the original one."""
    mapping = get_pinterest_board_mapping()
    eligible_boards = []
    
    # Simulate smart routing to find all eligible boards
    tags_and_type = (product_data.get('product_type', '') + ' ' + product_data.get('tags', '')).lower()
    for board, keywords in mapping.items():
        if board != original_board and any(k in tags_and_type for k in keywords):
            eligible_boards.append(board)
            
    if eligible_boards:
        return random.choice(eligible_boards)
    # Fallback to a random board if no strict match
    return random.choice([b for b in mapping.keys() if b != original_board])

# ── Main Loop Logic ───────────────────────────────────────────────────────────
def main():
    args = parse_args()
    print("=========================================================")
    print(" 🚀 Starting Pinterest Analytics & Evergreen Loop (API Mode)")
    if args.batch_size > 0:
        print(f" 📦 Batch Mode: index={args.batch_index}, size={args.batch_size}")
    print("=========================================================")
    
    client = PinterestClient()
    
    if not client.login():
        print("[ERROR] Pinterest login failed.")
        return
        
    # 1. Try to fetch from API boards (limits to recent 60 days)
    top_pins = get_top_performing_pins(client, limit=args.limit, days=args.days)
    
    # 2. Fallback to scraping the Analytics URL for actual historical viral pins
    if not top_pins:
        print("[INFO] No eligible recent pins found via API. Switching to Analytics Dashboard fallback.")
        analytics_urls = get_top_performing_pins_analytics(client)
        
        seen_handles = set()
        deduped = []
        for url in analytics_urls:
            if args.limit and args.limit > 0 and len(deduped) >= args.limit:
                break
                
            data = get_pin_details_api(client, url)
            if not data:
                continue
                
            saves = int(data.get('repin_count') or data.get('save_count') or 0)
            if saves == 0:
                saves = int(data.get('aggregated_pin_data', {}).get('saves') or 0)
            if saves == 0:
                saves = int(data.get('pin_metrics', {}).get('saves') or 0)
                
            link = data.get('link') or data.get('url') or ''
            handle = extract_shopify_handle(link)
            if not handle:
                handle = extract_shopify_handle(data.get('description', ''))
                
            if handle and handle not in seen_handles:
                seen_handles.add(handle)
                deduped.append({'pin_url': url, 'saves': saves, 'handle': handle})
                
        deduped.sort(key=lambda x: x['saves'], reverse=True)
        top_pins = deduped
        
    if not top_pins:
        print("[INFO] No eligible pins found via API or Analytics. Exiting.")
        return

    # Filter for highly engaged pins before batching
    eligible_pins = [p for p in top_pins if p['saves'] >= VIRAL_SAVES_THRESHOLD]
    
    print(f"\n[INFO] Total highly engaged pins fetched (>= {VIRAL_SAVES_THRESHOLD} saves): {len(eligible_pins)}")
    
    if args.batch_size > 0:
        start = args.batch_index * args.batch_size
        end = start + args.batch_size
        slice_pins = eligible_pins[start:end]
        print(f"[Batch] Processing slice [{start}:{end}] — {len(slice_pins)} pins")
    else:
        slice_pins = eligible_pins

    if not slice_pins:
        print("[INFO] No highly engaged pins to process in this batch. Exiting.")
        return

    for pin_data in slice_pins:
        pin_url = pin_data['pin_url']
        saves = pin_data['saves']
        handle = pin_data['handle']
        
        print(f"\n🔍 Analyzing Pin: {pin_url}")
        print(f"   => Engagement: {saves} saves detected.")
        
        if not handle:
            print("   [WARN] Could not extract a valid Shopify product handle from this pin. Skipping.")
            time.sleep(3)
            continue
        
        print("   🔥 Highly engaged pin detected! Validating Shopify Stock...")
            
        product = get_product_by_handle(handle)
                
        if product and is_in_stock(product):
            print("   ✅ Product is IN STOCK. Executing Evergreen Re-Pin.")
            new_board = get_new_board(None, product)
                
            boards = client.fetch_boards()
            board_id = next((b['id'] for b in boards if b['name'] == new_board), None)
            if not board_id and boards:
                board_id = boards[0]['id']
                new_board = boards[0]['name']
                
            # Generate fresh text for the re-pin
            title = content_generator.generate_pinterest_title(product)
            desc = content_generator.generate_pinterest_description(product, new_board)
                
            images = product.get("images", [])
            img_url = images[0].get("src") if images else None
            if not img_url:
                print("   [WARN] Product has no images. Skipping.")
                continue
            local_img = download_image_to_temp(img_url)
            if not local_img:
                continue
                    
            prod_url = f"{SHOPIFY_STORE}/products/{handle}?utm_source=pinterest&utm_medium=repin"
                
            print(f"   📌 Re-pinning to new board: {new_board}")
            client.create_pin(
                image_path=local_img, 
                title=title, 
                description=desc, 
                board_id=board_id, 
                url=prod_url, 
                alt_text=f"{product.get('title')} styling"
            )
                
            if os.path.exists(local_img):
                os.unlink(local_img)
                
        else:
            if not product:
                print(f"   [WARN] Product {handle} not found in Shopify (likely deleted). Executing Traffic Hijack Loop.")
            else:
                print("   ❌ Product is OUT OF STOCK. Executing Traffic Hijack Loop.")
                    
            replacement = find_in_stock_replacement(product, handle)
                
            if replacement:
                rep_handle = replacement.get("handle")
                print(f"   🔄 Found Replacement: {rep_handle}")
                    
                # 1. 301 Redirect to catch existing click traffic
                create_shopify_redirect(handle, rep_handle)
                    
                # 2. Piggyback Algorithm (Pin replacement to same board)
                target_board = get_new_board(None, replacement)
                    
                boards = client.fetch_boards()
                board_id = next((b['id'] for b in boards if b['name'] == target_board), None)
                if not board_id and boards:
                    board_id = boards[0]['id']
                    target_board = boards[0]['name']
                        
                title = content_generator.generate_pinterest_title(replacement)
                desc = content_generator.generate_pinterest_description(replacement, target_board)
                    
                images = replacement.get("images", [])
                img_url = images[0].get("src") if images else None
                if not img_url:
                    print("   [WARN] Replacement product has no images. Skipping piggyback.")
                    continue
                    
                local_img = download_image_to_temp(img_url)
                if not local_img:
                    continue
                        
                prod_url = f"{SHOPIFY_STORE}/products/{rep_handle}?utm_source=pinterest&utm_medium=piggyback"
                    
                print(f"   📌 Piggybacking new product onto relevant board: {target_board}")
                client.create_pin(
                    image_path=local_img, 
                    title=title, 
                    description=desc, 
                    board_id=board_id, 
                    url=prod_url, 
                    alt_text=f"{replacement.get('title')} fashion"
                )
                    
                if os.path.exists(local_img):
                    os.unlink(local_img)
            else:
                print("   [WARN] No in-stock replacement found. Skipping.")
            
        time.sleep(random.randint(5, 12)) # Human-like delay between actions
        
    print("\n✅ Analytics Loop Complete.")

if __name__ == "__main__":
    main()