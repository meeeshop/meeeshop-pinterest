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
from pathlib import Path
import requests
from datetime import datetime, timedelta

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
    data = _shopify_get("products.json", {"handle": handle})
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

def find_in_stock_replacement(out_product):
    """Find the best in-stock alternative in the same product type."""
    ptype = out_product.get("product_type", "")
    data = _shopify_get("products.json", {"product_type": ptype, "limit": 50})
    pool = [p for p in data.get("products", []) if is_in_stock(p) and p.get("id") != out_product.get("id")]
    
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

# ── API Pin Fetcher ───────────────────────────────────────────────────────────
def get_top_performing_pins(client, limit=5, days=30):
    """Fetch recent pins natively via py3-pinterest and sort by actual saves."""
    print(f"   [API] Fetching pins from the last {days} days across boards...")
    boards = client.fetch_boards()
    
    recent_pins = []
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for board in boards:
        board_id = board.get('id')
        if not board_id:
            continue
            
        try:
            # Use raw py3-pinterest client to get full pin data including stats
            board_pins = client.client.board_feed(board_id=board_id, page_size=25)
            for pin in (board_pins or []):
                # Parse creation date
                raw_ts = pin.get('created_at') or pin.get('created_time') or (pin.get('pin_join') or {}).get('created_at', '')
                if not raw_ts:
                    continue
                    
                try:
                    pin_date = datetime.fromisoformat(raw_ts.replace("Z", "+00:00").split("+")[0])
                    if pin_date < cutoff_date:
                        continue # Pin is too old
                except ValueError:
                    continue
                    
                # Extract engagement (saves/repins) checking all possible Pinterest API keys
                saves = int(pin.get('repin_count') or pin.get('save_count') or 0)
                if saves == 0:
                    saves = int(pin.get('aggregated_pin_data', {}).get('saves') or 0)
                if saves == 0:
                    saves = int(pin.get('pin_metrics', {}).get('saves') or 0)
                    
                # Extract Shopify handle from the outbound link
                link = pin.get('link') or pin.get('url') or ''
                handle = None
                link_match = re.search(r'meeeshop\.com/products/([a-z0-9\-]+)', link.lower())
                if link_match:
                    handle = link_match.group(1)
                    
                if handle:
                    recent_pins.append({
                        'pin_id': pin.get('id'),
                        'pin_url': f"https://www.pinterest.com/pin/{pin.get('id')}/",
                        'saves': saves,
                        'handle': handle,
                        'board_name': board.get('name')
                    })
        except Exception as e:
            print(f"   [WARN] Failed to fetch pins for board {board.get('name')}: {e}")
            
        time.sleep(1) # Gentle rate limiting between board fetches
        
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
            
    return deduped_pins[:limit]

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
    print("=========================================================")
    print(" 🚀 Starting Pinterest Analytics & Evergreen Loop (API Mode)")
    print("=========================================================")
    
    client = PinterestClient()
    
    if not client.login():
        print("[ERROR] Pinterest login failed.")
        return
        
    top_pins = get_top_performing_pins(client, limit=5, days=30)
    
    if not top_pins:
        print("[INFO] No eligible pins found to analyze today.")
        return
        
    for pin_data in top_pins:
        pin_url = pin_data['pin_url']
        saves = pin_data['saves']
        handle = pin_data['handle']
        
        print(f"\n🔍 Analyzing Pin: {pin_url}")
        print(f"   => Engagement: {saves} saves detected.")
        
        if not handle:
            print("   [WARN] Could not extract a valid Shopify product handle from this pin. Skipping.")
            time.sleep(3)
            continue
        
        if saves >= VIRAL_SAVES_THRESHOLD:
            print("   🔥 Highly engaged pin detected! Validating Shopify Stock...")
            
            product = get_product_by_handle(handle)
            if not product:
                print(f"   [WARN] Product {handle} not found in Shopify.")
                continue
                
            if is_in_stock(product):
                print("   ✅ Product is IN STOCK. Executing Evergreen Re-Pin.")
                new_board = get_new_board(None, product)
                
                # Generate fresh text for the re-pin
                title = content_generator.generate_pinterest_title(product)
                desc = content_generator.generate_pinterest_description(product, new_board)
                
                img_url = product.get("images", [{}])[0].get("src")
                prod_url = f"{SHOPIFY_STORE}/products/{handle}?utm_source=pinterest&utm_medium=repin"
                
                print(f"   📌 Re-pinning to new board: {new_board}")
                client.create_pin(
                    image=img_url, 
                    title=title, 
                    desc=desc, 
                    board=new_board, 
                    url=prod_url, 
                    alt_text=f"{product.get('title')} styling"
                )
                
            else:
                print("   ❌ Product is OUT OF STOCK. Executing Traffic Hijack Loop.")
                replacement = find_in_stock_replacement(product)
                
                if replacement:
                    rep_handle = replacement.get("handle")
                    print(f"   🔄 Found Replacement: {rep_handle}")
                    
                    # 1. 301 Redirect to catch existing click traffic
                    create_shopify_redirect(handle, rep_handle)
                    
                    # 2. Piggyback Algorithm (Pin replacement to same board)
                    title = content_generator.generate_pinterest_title(replacement)
                    target_board = get_new_board(None, replacement)
                    desc = content_generator.generate_pinterest_description(replacement, target_board)
                    
                    img_url = replacement.get("images", [{}])[0].get("src")
                    prod_url = f"{SHOPIFY_STORE}/products/{rep_handle}?utm_source=pinterest&utm_medium=piggyback"
                    
                    print(f"   📌 Piggybacking new product onto relevant board: {target_board}")
                    client.create_pin(
                        image=img_url, 
                        title=title, 
                        desc=desc, 
                        board=target_board, 
                        url=prod_url, 
                        alt_text=f"{replacement.get('title')} fashion"
                    )
                else:
                    print("   [WARN] No in-stock replacement found. Skipping.")
        else:
            print("   ❄️ Engagement below threshold. Moving on.")
            
        time.sleep(random.randint(5, 12)) # Human-like delay between actions
        
    print("\n✅ Analytics Loop Complete.")

if __name__ == "__main__":
    main()