#!/usr/bin/env python3
"""
convert_cookies.py — Convert text-based cookies to pickle format
Converts manual cookie export (name = value) to pickle format for selenium
"""

import pickle
from pathlib import Path

def convert_cookies_to_pickle():
    """Convert text cookies to pickle format"""

    text_file = Path(__file__).parent / ".pinterest_cookies"
    pickle_file = Path(__file__).parent / ".pinterest_cookies.pkl"

    if not text_file.exists():
        print("❌ Cookies text file not found")
        return False

    print(f"📖 Reading text cookies from: {text_file}")

    # Parse text format (name = value on each line)
    cookies = []
    text_content = text_file.read_text(encoding="utf-8")

    for line in text_content.strip().split('\n'):
        if '=' in line:
            parts = line.split('=', 1)
            if len(parts) == 2:
                name = parts[0].strip()
                value = parts[1].strip()

                # Create cookie dict (selenium format)
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": "pinterest.com",
                    "path": "/",
                }
                cookies.append(cookie)
                print(f"  ✓ {name}: {value[:30]}...")

    if not cookies:
        print("❌ No cookies found in text file")
        return False

    print(f"\n📦 Found {len(cookies)} cookies")
    print(f"💾 Writing to pickle format: {pickle_file}")

    # Save as pickle (binary format)
    with open(pickle_file, "wb") as f:
        pickle.dump(cookies, f)

    # Verify pickle is readable
    try:
        with open(pickle_file, "rb") as f:
            loaded = pickle.load(f)
        print(f"✅ Verified: {len(loaded)} cookies in pickle file")
        return True
    except Exception as e:
        print(f"❌ Error verifying pickle: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🍪 CONVERTING PINTEREST COOKIES TO PICKLE FORMAT")
    print("=" * 60)
    print()

    success = convert_cookies_to_pickle()

    print()
    print("=" * 60)
    if success:
        print("✅ CONVERSION COMPLETE")
        print("\nNext: Run test_posting.py again")
    else:
        print("❌ CONVERSION FAILED")
    print("=" * 60)
