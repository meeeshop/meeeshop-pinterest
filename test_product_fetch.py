"""
Test script to verify product fetching logic locally
Tests the fetch_all_eligible_products function with mock data
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest.pinterest_daily import fetch_all_eligible_products
from pinterest.shopify_products import ShopifyClient

def test_product_fetch():
    """Test fetching eligible products from Shopify"""

    print("=" * 60)
    print("PRODUCT FETCH TEST")
    print("=" * 60)

    # Load credentials
    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")

    if not shopify_url or not shopify_token:
        print("❌ Missing Shopify credentials in .env")
        return False

    print(f"✓ Using store: {shopify_url}")

    # Initialize Shopify client
    shopify = ShopifyClient(shopify_url, shopify_token)

    # Create empty history (no previous posts)
    history = {
        "posts": [],
        "board_last_used": {},
        "daily_count": 0,
        "last_post_time": None,
        "board_rotation_cursor": 0,
    }

    # Test 1: Fetch with min_stock=20
    print("\n[TEST 1] Fetching products with stock >= 20...")
    eligible = fetch_all_eligible_products(shopify, history, min_stock=20)

    if not eligible:
        print("❌ FAIL: No eligible products returned")
        return False

    print(f"✓ PASS: Found {len(eligible)} eligible products")

    # Show sample products
    print("\nFirst 5 eligible products:")
    for i, prod in enumerate(eligible[:5], 1):
        max_stock = max(
            (v.get("inventory_quantity", 0) for v in prod.get("variants", [])),
            default=0
        )
        print(f"  {i}. {prod.get('title')} (Stock: {max_stock})")

    # Test 2: Verify all have stock >= 20
    print("\n[TEST 2] Verifying all products have stock >= 20...")
    all_valid = True
    for prod in eligible:
        max_stock = max(
            (v.get("inventory_quantity", 0) for v in prod.get("variants", [])),
            default=0
        )
        if max_stock < 20:
            print(f"❌ Invalid: {prod.get('title')} has stock {max_stock}")
            all_valid = False

    if all_valid:
        print(f"✓ PASS: All {len(eligible)} products have stock >= 20")
    else:
        print("❌ FAIL: Some products have stock < 20")
        return False

    # Test 3: Test with 10-day history filter
    print("\n[TEST 3] Testing 10-day history filter...")

    # Add one product to recent history (posted 5 days ago)
    if eligible:
        test_product_id = eligible[0].get("id")
        history["posts"] = [{
            "product_id": test_product_id,
            "title": eligible[0].get("title"),
            "board": "test",
            "timestamp": (datetime.now() - timedelta(days=5)).isoformat(),
        }]

    eligible_filtered = fetch_all_eligible_products(shopify, history, min_stock=20)

    if test_product_id and test_product_id in [p.get("id") for p in eligible_filtered]:
        print(f"❌ FAIL: Product posted 5 days ago still in results (should be filtered)")
        return False
    else:
        print(f"✓ PASS: Product from 5 days ago correctly filtered out")
        print(f"  Before filter: {len(eligible)} products")
        print(f"  After filter: {len(eligible_filtered)} products")

    # Test 4: Stock threshold edge case
    print("\n[TEST 4] Testing stock threshold edge case...")
    history["posts"] = []  # Clear history

    # Try with min_stock=1 (should get more results)
    all_products = fetch_all_eligible_products(shopify, history, min_stock=1)
    high_stock = fetch_all_eligible_products(shopify, history, min_stock=20)

    if len(all_products) >= len(high_stock):
        print(f"✓ PASS: min_stock=1 returned {len(all_products)} vs min_stock=20 returned {len(high_stock)}")
    else:
        print(f"❌ FAIL: Unexpected results - min_stock=1: {len(all_products)}, min_stock=20: {len(high_stock)}")
        return False

    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = test_product_fetch()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
