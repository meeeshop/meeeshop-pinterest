#!/usr/bin/env python3
"""
pinterest_analytics_loop.py — Evergreen Traffic & OOS Hijack Loop
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Uses py3-pinterest API to fetch your boards and recent pins natively.
2. Evaluates each pin's API engagement stats (Saves) and extracts the Shopify URL.
3. If highly engaged -> Checks Shopify inventory for that product handle.
4. IF IN STOCK: Re-pins to a new overlapping relevant board with fresh image style.
5. IF OUT OF STOCK: Creates a 301 redirect in Shopify & piggybacks the replacement pin.

NOTE: Selenium analytics fallback has been REMOVED (account safety — Pinterest
detects and flags headless Chrome automation). py3pin native API is used exclusively.
"""

import os
import sys
import time
import json
import random
import re
import argparse
from pathlib import Path
import traceback
import requests
import tempfile
from datetime import datetime, timedelta
# Selenium removed — Pinterest flags headless Chrome automation

# ── Local Imports ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pinterest_client import PinterestClient
from shopify_products import get_pinterest_board_mapping, ShopifyClient
import content_generator
import image_overlay
from daily_pin_tracker import DailyPinTracker

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
STORE_BASE_URL = get_secret("STORE_BASE_URL")

API_VER = "2024-10"
HEADERS = {"X-Shopify-Access-Token": SHOPIFY_TOKEN, "Content-Type": "application/json"}

# Thresholds for a pin to be considered "Viral" or highly engaged
VIRAL_SAVES_THRESHOLD = 10 
VIRAL_IMPRESSIONS_THRESHOLD = 2000
VIRAL_ENGAGEMENTS_THRESHOLD = 15
VIRAL_OUTBOUND_CLICKS_THRESHOLD = 5

# State tracking file to prevent repinning the same pin
HISTORY_FILE = ROOT / "repin_history.json"

def load_repin_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[WARN] Failed to load repin history: {e}")
    return set()

def save_repin_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(list(history), f)
    except Exception as e:
        print(f"[WARN] Failed to save repin history: {e}")

def parse_args():
    parser = argparse.ArgumentParser(description="Pinterest Analytics & Evergreen Loop")
    parser.add_argument("--batch-size", type=int, default=0, help="Number of pins to process per batch (0 = all)")
    parser.add_argument("--batch-index", type=int, default=0, help="Batch index to process")
    parser.add_argument("--limit", type=int, default=0, help="Max total pins to select before batching (0 = all)")
    parser.add_argument("--days", type=int, default=60, help="Number of days to look back for pins")
    parser.add_argument("--strategy", type=str, choices=["daily", "biweekly"], default="daily", help="Strategy to run ('daily' or 'biweekly')")
    parser.add_argument("--template", type=int, default=13, help="Template index to use for image overlay")
    parser.add_argument("--ignore-history", action="store_true", help="Ignore repin history to allow testing")
    return parser.parse_args()

# ── Shopify API Helpers ───────────────────────────────────────────────────────
_shopify_client = None

def get_shopify_client():
    global _shopify_client
    if _shopify_client is None:
        _shopify_client = ShopifyClient(SHOPIFY_STORE, SHOPIFY_TOKEN)
    return _shopify_client

def _shopify_post(endpoint, payload):
    base = SHOPIFY_STORE.rstrip('/')
    url = f"{base}/admin/api/{API_VER}/{endpoint}"
    response = requests.post(url, headers=HEADERS, json=payload)
    if response.status_code not in (200, 201):
        print(f"[ERROR] Shopify POST failed: {response.text}")
    return response.json()

def get_product_by_handle(handle):
    """Fetch product details by handle to check stock."""
    return get_shopify_client().get_product_by_handle(handle)

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

    client = get_shopify_client()
    products = client.get_products(limit=250, status="active", product_type=ptype)
    pool = [p for p in products if is_in_stock(p) and (not out_product or p.get("id") != out_product.get("id"))]
    
    if pool:
        return random.choice(pool)
    if ptype:
        # Fallback to any product
        products = client.get_products(limit=250, status="active")
        pool = [p for p in products if is_in_stock(p) and (not out_product or p.get("id") != out_product.get("id"))]
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
    res = _shopify_post("redirects.json", payload)
    if "errors" in res:
        print(f"    [Shopify] Note: Redirect issue (may already exist): {res['errors']}")
    return res

def extract_shopify_handle(text):
    """Extracts meeeshop handle from text/URLs."""
    if not STORE_BASE_URL:
        print("[WARN] STORE_BASE_URL is not set in secrets; cannot extract Shopify handles.")
        return None
    domain = STORE_BASE_URL.replace("https://", "").replace("http://", "").strip("/")
    match = re.search(rf'{re.escape(domain)}/products/([a-z0-9\-]+)', str(text).lower())
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

# ── Analytics Fallback — Selenium REMOVED for account safety ─────────────────
# Pinterest detects and flags headless Chrome automation sessions.
# The py3pin native board_feed API (get_top_performing_pins) is the only safe
# method to identify top-performing pins without risking a ban.
# If no qualifying pins are found via the API, we simply exit gracefully.

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
                        saves = int((pin.get('aggregated_pin_data') or {}).get('saves') or 0)
                    if saves == 0:
                        saves = int((pin.get('pin_metrics') or {}).get('saves') or 0)
                        
                    pin_metrics = pin.get('pin_metrics') or {}
                    aggregated = pin.get('aggregated_pin_data') or {}
                    
                    impressions = int(pin_metrics.get('impressions') or aggregated.get('impressions') or 0)
                    engagements = int(pin_metrics.get('engagements') or aggregated.get('engagements') or 0)
                    outbound_clicks = int(pin_metrics.get('outbound_clicks') or aggregated.get('outbound_clicks') or 0)
                    pin_clicks = int(pin_metrics.get('pin_clicks') or aggregated.get('pin_clicks') or 0)
                        
                    link = pin.get('link') or pin.get('url') or ''
                    handle = extract_shopify_handle(link)
                    if not handle:
                        handle = extract_shopify_handle(pin.get('description', ''))
                        
                    if not handle:
                        total_skipped_handle += 1
                        continue

                    image_url = pin.get('image_large_url') or pin.get('images', {}).get('orig', {}).get('url')
                    if not image_url and 'images' in pin:
                        # Fallback for other image sizes
                        for size in ['1200x', '736x', '400x300']:
                            if size in pin['images']:
                                image_url = pin['images'][size].get('url')
                                break

                    recent_pins.append({
                        'pin_id': pin.get('id'),
                        'pin_url': f"https://www.pinterest.com/pin/{pin.get('id')}/",
                        'saves': saves,
                        'impressions': impressions,
                        'engagements': engagements,
                        'outbound_clicks': outbound_clicks,
                        'pin_clicks': pin_clicks,
                        'handle': handle,
                        'board_name': board.get('name'),
                        'image_url': image_url
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

    # ── Daily pin cap guard ───────────────────────────────────────────────────
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    tracker = DailyPinTracker()
    pins_to_post = 3 if args.strategy == "biweekly" else 1
    if not dry_run and not tracker.can_post(n=pins_to_post):
        print(f"[DailyPinTracker] Daily cap reached ({tracker.total}/{tracker.cap}). Skipping analytics loop.")
        return
    print(f"[DailyPinTracker] {tracker.summary()}")
    print("=========================================================")
    print(" 🚀 Starting Pinterest Analytics & Evergreen Loop (API Mode)")
    if args.batch_size > 0:
        print(f" 📦 Batch Mode: index={args.batch_index}, size={args.batch_size}")
    print("=========================================================")
    
    client = PinterestClient()
    
    if not client.login():
        print("[ERROR] Pinterest login failed.")
        return
        
    # Fetch top-performing pins via py3pin native API (safe — no Selenium)
    top_pins = get_top_performing_pins(client, limit=args.limit, days=args.days)

    if not top_pins:
        print("[INFO] No eligible recent pins found via py3pin API. Exiting gracefully.")
        return

    # Filter for highly engaged pins before batching
    repin_history = load_repin_history()
    
    def is_highly_engaged(p):
        return (p.get('saves', 0) >= VIRAL_SAVES_THRESHOLD or
                p.get('impressions', 0) >= VIRAL_IMPRESSIONS_THRESHOLD or
                p.get('engagements', 0) >= VIRAL_ENGAGEMENTS_THRESHOLD or
                p.get('outbound_clicks', 0) >= VIRAL_OUTBOUND_CLICKS_THRESHOLD)
                
    eligible_pins = []
    for p in top_pins:
        pin_id = p.get('pin_id')
        if not args.ignore_history and pin_id and str(pin_id) in repin_history:
            print(f"   [INFO] Skipping pin {pin_id} as it was already repinned previously.")
            continue
        if is_highly_engaged(p):
            eligible_pins.append(p)
    
    print(f"\n[INFO] Total highly engaged, unpinned pins fetched: {len(eligible_pins)}")
    
    if args.batch_size > 0:
        start = args.batch_index * args.batch_size
        end = start + args.batch_size
        slice_pins = eligible_pins[start:end]
        print(f"[Batch] Processing slice [{start}:{end}] — {len(slice_pins)} pins")
    else:
        slice_pins = eligible_pins

    if not slice_pins:
        print("[INFO] No highly engaged pins to process in this batch — skipping execution to avoid spam.")
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
            content = content_generator.generate_content_package(product, new_board)
            title = content["pin_title"]
            hashtags_str = " ".join(content["hashtags"]) + " #USAWomensFashion #WomensStyle #USStyle"
            desc = f'{content["pin_description"]}\n\n{hashtags_str}'
                
            images = product.get("images", [])
            
            if not images:
                print("   [WARN] Product has no images. Skipping.")
                continue
                
            img_url = images[0].get("src") if images else None
            if not img_url:
                print("   [WARN] Product has no images. Skipping.")
                continue
                
            local_img = download_image_to_temp(img_url)
            if not local_img:
                continue

            additional_image_files = []
            if len(images) > 1:
                extra_urls = [img.get("src") for img in images[1:] if img.get("src")][:3]
                for url in extra_urls:
                    temp_img = download_image_to_temp(url)
                    if temp_img:
                        additional_image_files.append(temp_img)

            # Apply style-rotating overlay (hero/card/collage — avoids repetitive look)
            price = product.get("variants", [{}])[0].get("price", "") if product else ""
            overlaid_img = image_overlay.create_pin_image(
                product_image_path=local_img,
                title=product.get("title", ""),
                price=price,
                cta="Shop Now",
                board_name=new_board,
                additional_image_paths=additional_image_files,
                force_style=os.getenv("FORCE_IMAGE_STYLE", "auto") or "auto",
            )
            if overlaid_img:
                if os.path.exists(local_img):
                    os.unlink(local_img)
                local_img = overlaid_img
                    
            top_keyword = content["keywords"][0].replace(' ', '-') if content.get("keywords") else "fashion"
            prod_url = f"{STORE_BASE_URL.rstrip('/')}/products/{handle}?utm_source=pinterest&utm_medium=repin&utm_term={top_keyword}"
                
            print(f"   📌 Re-pinning to new board: {new_board}")
            success, pin_id = client.create_pin(
                image_path=local_img, 
                title=title, 
                description=desc, 
                board_id=board_id, 
                url=prod_url, 
                alt_text=content.get("pin_alt_text", f"{product.get('title')} styling")
            )
            if success and pin_id:
                print(f"   ✅ Successfully created Evergreen Pin! URL: https://www.pinterest.com/pin/{pin_id}/")
            else:
                print(f"   ❌ Failed to create Evergreen Pin.")
                
            if os.path.exists(local_img):
                os.unlink(local_img)
                
        else:
            if args.strategy == "daily":
                print(f"   [INFO] Product '{handle}' is OUT OF STOCK or not found. Skipping piggyback hijacking in daily strategy.")
                continue

            if not product:
                print(f"   [INFO] Original product '{handle}' not found (likely deleted). Hijacking traffic to similar in-stock product.")
            else:
                print(f"   [INFO] Original product '{handle}' is OUT OF STOCK. Hijacking traffic to similar in-stock product.")
                    
            replacement = find_in_stock_replacement(product, handle)
                
            if replacement:
                rep_handle = replacement.get("handle")
                print(f"   🔄 Found active replacement: {rep_handle}")
                    
                # 1. 301 Redirect to catch existing click traffic
                create_shopify_redirect(handle, rep_handle)
                    
                # 2. Piggyback Algorithm (Pin replacement to same board)
                target_board = get_new_board(None, replacement)
                    
                boards = client.fetch_boards()
                board_id = next((b['id'] for b in boards if b['name'] == target_board), None)
                if not board_id and boards:
                    board_id = boards[0]['id']
                    target_board = boards[0]['name']
                        
                content = content_generator.generate_content_package(replacement, target_board)
                title = content["pin_title"]
                hashtags_str = " ".join(content["hashtags"]) + " #USAWomensFashion #WomensStyle #USStyle"
                desc = f'{content["pin_description"]}\n\n{hashtags_str}'
                    
                # Use the original viral pin's image, not the replacement product's image!
                img_url = pin_data.get('image_url')
                additional_image_files = []
                
                images = replacement.get("images", [])
                
                if not img_url:
                    # Fallback to replacement product image
                    img_url = images[0].get("src") if images else None
                    if len(images) > 1:
                        extra_urls = [img.get("src") for img in images[1:] if img.get("src")][:3]
                        for url in extra_urls:
                            temp_img = download_image_to_temp(url)
                            if temp_img:
                                additional_image_files.append(temp_img)
                else:
                    # If using original viral pin's image, we can still add replacement images as variants
                    if images:
                        extra_urls = [img.get("src") for img in images if img.get("src")][:3]
                        for url in extra_urls:
                            temp_img = download_image_to_temp(url)
                            if temp_img:
                                additional_image_files.append(temp_img)
                    
                if not img_url:
                    print("   [WARN] Could not find image for piggyback. Skipping.")
                    continue
                    
                local_img = download_image_to_temp(img_url)
                if not local_img:
                    continue

                # Apply style-rotating overlay for piggyback pin
                price = replacement.get("variants", [{}])[0].get("price", "") if replacement else ""
                overlaid_img = image_overlay.create_pin_image(
                    product_image_path=local_img,
                    title=replacement.get("title", ""),
                    price=price,
                    cta="Shop Now",
                    board_name=target_board,
                    additional_image_paths=additional_image_files,
                    force_style=os.getenv("FORCE_IMAGE_STYLE", "auto") or "auto",
                )
                if overlaid_img:
                    if os.path.exists(local_img):
                        os.unlink(local_img)
                    local_img = overlaid_img
                        
                top_keyword = content["keywords"][0].replace(' ', '-') if content.get("keywords") else "fashion"
                prod_url = f"{STORE_BASE_URL.rstrip('/')}/products/{rep_handle}?utm_source=pinterest&utm_medium=piggyback&utm_term={top_keyword}"
                    
                print(f"   📌 Piggybacking new product '{rep_handle}' onto relevant board '{target_board}'")
                success, pin_id = client.create_pin(
                    image_path=local_img, 
                    title=title, 
                    description=desc, 
                    board_id=board_id, 
                    url=prod_url, 
                    alt_text=content.get("pin_alt_text", f"{replacement.get('title')} fashion")
                )
                if success and pin_id:
                    print(f"   ✅ Successfully created Piggyback Pin! URL: https://www.pinterest.com/pin/{pin_id}/")
                    if pin_data.get('pin_id'):
                        repin_history.add(str(pin_data.get('pin_id')))
                else:
                    print(f"   ❌ Failed to create Piggyback Pin.")
                    
                if os.path.exists(local_img):
                    os.unlink(local_img)
            else:
                print("   [WARN] No in-stock replacement found. Skipping.")

        # Track in repin history and daily cap
        if product and is_in_stock(product) and pin_data.get('pin_id'):
            repin_history.add(str(pin_data.get('pin_id')))
            if not dry_run:
                tracker.record(n=1, source="analytics_loop")

        # Human-like delay between pins (30–90 seconds — looks organic, not bot)
        delay = random.randint(30, 90)
        print(f"   ⏳ Waiting {delay}s before next pin (organic pacing)...")
        time.sleep(delay)

    save_repin_history(repin_history)
    print(f"\n✅ Analytics Loop Complete. {tracker.summary()}")

if __name__ == "__main__":
    main()