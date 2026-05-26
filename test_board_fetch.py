"""
Test script to verify board fetching fetches ALL boards with pagination
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_board_fetch():
    """Test fetching all boards with pagination"""

    print("=" * 70)
    print("BOARD FETCH PAGINATION TEST")
    print("=" * 70)

    pinterest = PinterestClient()

    print("\n[Step 1] Logging in to Pinterest...")
    if not pinterest.login():
        print("❌ Login failed")
        return False

    print("✓ Login successful")

    print("\n[Step 2] Fetching all boards with pagination...")
    boards = pinterest.fetch_boards()

    if not boards:
        print("❌ No boards returned")
        return False

    print(f"\n✓ Fetched {len(boards)} total boards")
    print("\nFirst 10 boards:")
    for i, board in enumerate(boards[:10], 1):
        print(f"  {i}. {board['name']} (ID: {board['id']})")

    if len(boards) > 10:
        print(f"  ... and {len(boards) - 10} more boards")

    print("\n" + "=" * 70)
    if len(boards) > 41:
        print(f"✓ SUCCESS: Fetched {len(boards)} boards (more than 41)")
    else:
        print(f"⚠ Only {len(boards)} boards (pagination may not be working)")
    print("=" * 70)

    return len(boards) > 41

if __name__ == "__main__":
    try:
        success = test_board_fetch()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
