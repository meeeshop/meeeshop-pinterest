"""
diagnose_inventory.py — Check Shopify inventory categories and stock levels
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from shopify_products import ShopifyClient
from pinterest_daily_v2 import get_product_main_category

def run_diagnostics():
    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")

    client = ShopifyClient(shopify_url, shopify_token)
    products = client.get_all_products(status="active")

    print(f"Total Active Products in Shopify: {len(products)}")

    cat_counts = {}
    stock_by_cat = {}
    
    for p in products:
        cat = get_product_main_category(p.get("title", ""), p.get("product_type", ""))
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        
        max_stock = max([v.get("inventory_quantity", 0) for v in p.get("variants", [])], default=0)
        if cat not in stock_by_cat:
            stock_by_cat[cat] = []
        stock_by_cat[cat].append(max_stock)

    print("\n--- PRODUCT BREAKDOWN BY CATEGORY ---")
    for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        stocks = stock_by_cat[cat]
        over_15 = sum(1 for s in stocks if s >= 15)
        over_1 = sum(1 for s in stocks if s >= 1)
        print(f"Category '{cat}': Total = {count} | Stock >= 15: {over_15} | Stock >= 1: {over_1}")

    # Check posting history category breakdown
    history_file = Path(__file__).parent / "posting_history_v2.json"
    if history_file.exists():
        data = json.loads(history_file.read_text(encoding="utf-8"))
        posts = data.get("posts", [])
        print(f"\n--- POSTING HISTORY (Total posts: {len(posts)}) ---")
        post_cats = {}
        for post in posts[-20:]: # last 20 posts
            c = post.get("category", "unknown")
            post_cats[c] = post_cats.get(c, 0) + 1
            print(f"  - [{post.get('timestamp')[:16]}] {post.get('title')[:40]} (Cat: {c})")
        print("\nLast 20 Posts Category Summary:", post_cats)

if __name__ == "__main__":
    run_diagnostics()
