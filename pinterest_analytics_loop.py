#!/usr/bin/env python3
"""
pinterest_analytics_loop.py — Evergreen Traffic & OOS Hijack Loop
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Loads past pins from posting_history.json
2. Uses Selenium to navigate to the pin and scrape visible engagement (Saves).
3. If highly engaged -> Checks Shopify inventory.
4. IF IN STOCK: Re-pins to a new overlapping board.
5. IF OUT OF STOCK: Creates a 301 redirect to an in-stock replacement & piggybacks the pin.
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

# ── Selenium Scraper ──────────────────────────────────────────────────────────
def scrape_pin_saves(driver, pin_url):
    """Navigate to an individual pin and read its save/engagement count."""
    try:
        driver.get(pin_url)
        time.sleep(4) # Let DOM render
        
        # Look for the 'Saves' metric in the DOM text
        page_source = driver.page_source.lower()
        
        # Simple regex to catch generic numbers next to 'saves' (e.g. "12 saves", "1.5k saves")
        match = re.search(r'([0-9k\.]+)\s+saves?', page_source)
        if match:
            val_str = match.group(1).replace('k', '000').replace('.', '')
            return int(val_str)
            
    except Exception as e:
        print(f"    [WARN] Failed to scrape {pin_url}: {e}")
        
    return 0 # Return 0 if not found or no engagement

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
    print(" 🚀 Starting Pinterest Analytics & Evergreen Loop")
    print("=========================================================")
    
    history_file = ROOT / "posting_history.json"
    if not history_file.exists():
        print("[INFO] No posting_history.json found. Exiting.")
        return
        
    with open(history_file, 'r') as f:
        history = json.load(f)
        
    # Filter pins posted more than 3 days ago but less than 60 days ago
    cutoff_recent = datetime.now() - timedelta(days=3)
    cutoff_old = datetime.now() - timedelta(days=60)
    
    eligible_pins = []
    for post in history.get("posts", []):
        try:
            pt = datetime.fromisoformat(post.get("timestamp", ""))
            if cutoff_old < pt < cutoff_recent and "pin_url" in post: # Assuming pin_url is saved
                eligible_pins.append(post)
        except Exception:
            pass
            
    if not eligible_pins:
        print("[INFO] No eligible mature pins to analyze today.")
        return
        
    # Initialize Pinterest Selenium Client
    client = PinterestClient()
    if not client.login(PINTEREST_EMAIL, PINTEREST_PASSWORD):
        print("[ERROR] Pinterest login failed.")
        client.close()
        return
        
    # Analyze up to 5 random older pins per run to avoid Selenium burn-out
    pins_to_check = random.sample(eligible_pins, min(5, len(eligible_pins)))
    
    for pin_data in pins_to_check:
        pin_url = pin_data.get("pin_url")
        handle = pin_data.get("handle") or pin_data.get("product_id") # Depending on how you stored it
        original_board = pin_data.get("board")
        
        print(f"\n🔍 Analyzing Pin: {pin_url}")
        saves = scrape_pin_saves(client.driver, pin_url)
        print(f"   => Engagement: {saves} saves detected.")
        
        if saves >= VIRAL_SAVES_THRESHOLD:
            print("   🔥 Highly engaged pin detected! Validating Shopify Stock...")
            
            product = get_product_by_handle(handle)
            if not product:
                print(f"   [WARN] Product {handle} not found in Shopify.")
                continue
                
            if is_in_stock(product):
                print("   ✅ Product is IN STOCK. Executing Evergreen Re-Pin.")
                new_board = get_new_board(original_board, product)
                
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
                    desc = content_generator.generate_pinterest_description(replacement, original_board)
                    
                    img_url = replacement.get("images", [{}])[0].get("src")
                    prod_url = f"{SHOPIFY_STORE}/products/{rep_handle}?utm_source=pinterest&utm_medium=piggyback"
                    
                    print(f"   📌 Piggybacking new product onto viral board: {original_board}")
                    client.create_pin(
                        image=img_url, 
                        title=title, 
                        desc=desc, 
                        board=original_board, 
                        url=prod_url, 
                        alt_text=f"{replacement.get('title')} fashion"
                    )
                else:
                    print("   [WARN] No in-stock replacement found. Skipping.")
        else:
            print("   ❄️ Engagement below threshold. Moving on.")
            
        time.sleep(random.randint(5, 12)) # Human-like delay between actions
        
    print("\n✅ Analytics Loop Complete.")
    client.close()

if __name__ == "__main__":
    main()