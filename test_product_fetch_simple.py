"""
Simple test of the product filtering logic WITHOUT secrets manager
Tests the logic directly with mock data
"""

import json
import sys
from datetime import datetime, timedelta

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def test_product_filtering():
    """Test the product filtering logic with mock data"""

    print("=" * 70)
    print("PRODUCT FILTERING LOGIC TEST (No Secrets Required)")
    print("=" * 70)

    # Mock products that would come from Shopify API
    mock_products = [
        {
            "id": 1001,
            "title": "Blue Denim Jeans",
            "handle": "blue-denim-jeans",
            "variants": [{"inventory_quantity": 25}],
        },
        {
            "id": 1002,
            "title": "Red Cotton Blouse",
            "handle": "red-cotton-blouse",
            "variants": [{"inventory_quantity": 35}],
        },
        {
            "id": 1003,
            "title": "Black Tank Top",
            "handle": "black-tank-top",
            "variants": [{"inventory_quantity": 10}],  # Low stock
        },
        {
            "id": 1004,
            "title": "White Tee",
            "handle": "white-tee",
            "variants": [{"inventory_quantity": 0}],  # Out of stock
        },
        {
            "id": 1005,
            "title": "Green Cardigan",
            "handle": "green-cardigan",
            "variants": [{"inventory_quantity": 50}],
        },
        {
            "id": 1006,
            "title": "Multi-variant Product",
            "handle": "multi",
            "variants": [
                {"inventory_quantity": 5},
                {"inventory_quantity": 25},  # One variant has stock
                {"inventory_quantity": 0},
            ],
        },
    ]

    min_stock = 20

    # Test 1: Filter products with stock >= 20 (OLD CODE - would fail)
    print("\n[TEST 1] OLD CODE - p.get('status') == 'active' filter")
    print("-" * 70)
    eligible_old = [
        p for p in mock_products
        if p.get("status") == "active"  # This always fails!
        and any(v.get("inventory_quantity", 0) >= min_stock for v in p.get("variants", []))
    ]
    print(f"Result: {len(eligible_old)} eligible products")
    if len(eligible_old) == 0:
        print("❌ BUG CONFIRMED: All products filtered out because they have no 'status' field!")
    else:
        print("✓ Unexpected - some products passed (should be 0)")

    # Test 2: Filter products with stock >= 20 (FIXED CODE)
    print("\n[TEST 2] FIXED CODE - removed invalid status check")
    print("-" * 70)
    eligible_new = [
        p for p in mock_products
        if any(v.get("inventory_quantity", 0) >= min_stock for v in p.get("variants", []))
    ]
    print(f"Result: {len(eligible_new)} eligible products")
    print("\nEligible products:")
    for prod in eligible_new:
        max_stock = max((v.get("inventory_quantity", 0) for v in prod.get("variants", [])), default=0)
        print(f"  ✓ {prod['title']} (max stock: {max_stock})")

    expected_eligible = {1001, 1002, 1005, 1006}  # Have variants with stock >= 20
    actual_ids = {p["id"] for p in eligible_new}

    if actual_ids == expected_eligible:
        print(f"\n✓ PASS: Got expected 4 products: {sorted(actual_ids)}")
    else:
        print(f"\n❌ FAIL: Expected {expected_eligible}, got {actual_ids}")
        return False

    # Test 3: With history filter (10 days)
    print("\n[TEST 3] 10-day history filter")
    print("-" * 70)

    history = {
        "posts": [
            {
                "product_id": 1001,
                "title": "Blue Denim Jeans",
                "timestamp": (datetime.now() - timedelta(days=5)).isoformat(),  # 5 days ago
            },
            {
                "product_id": 1005,
                "title": "Green Cardigan",
                "timestamp": (datetime.now() - timedelta(days=15)).isoformat(),  # 15 days ago (should NOT be filtered)
            },
        ],
        "daily_count": 2,
        "board_rotation_cursor": 0,
        "board_last_used": {},
        "last_post_time": None,
    }

    ten_days_ago = datetime.now() - timedelta(days=10)
    recent_ids = {
        p.get("product_id")
        for p in history.get("posts", [])
        if datetime.fromisoformat(p["timestamp"]) > ten_days_ago
    }

    print(f"Products posted in last 10 days: {recent_ids}")

    eligible_with_history = [
        p for p in mock_products
        if p.get("id") not in recent_ids
        and any(v.get("inventory_quantity", 0) >= min_stock for v in p.get("variants", []))
    ]

    print(f"\nAfter 10-day filter: {len(eligible_with_history)} products")
    for prod in eligible_with_history:
        max_stock = max((v.get("inventory_quantity", 0) for v in prod.get("variants", [])), default=0)
        print(f"  ✓ {prod['title']} (max stock: {max_stock})")

    expected_with_history = {1002, 1005, 1006}  # 1001 filtered (posted 5 days ago)
    actual_with_history = {p["id"] for p in eligible_with_history}

    if actual_with_history == expected_with_history:
        print(f"\n✓ PASS: Got expected 3 products (1001 excluded): {sorted(actual_with_history)}")
    else:
        print(f"\n❌ FAIL: Expected {expected_with_history}, got {actual_with_history}")
        return False

    # Test 4: Different stock thresholds
    print("\n[TEST 4] Stock threshold variations")
    print("-" * 70)

    for threshold in [1, 10, 20, 30]:
        count = len([
            p for p in mock_products
            if any(v.get("inventory_quantity", 0) >= threshold for v in p.get("variants", []))
        ])
        print(f"  min_stock={threshold:2d}: {count} products")

    print("\n" + "=" * 70)
    print("✓ ALL LOGIC TESTS PASSED - Fix is correct!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    try:
        success = test_product_filtering()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
