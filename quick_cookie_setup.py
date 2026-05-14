#!/usr/bin/env python3
"""Quick cookie extraction - paste your cookies here."""

import json
import base64
from pathlib import Path

print("\n" + "=" * 80)
print("PINTEREST COOKIE EXTRACTION")
print("=" * 80 + "\n")

print("📌 Instructions:")
print("1. Open https://pinterest.com in Chrome (logged in)")
print("2. Press F12 → Application tab → Cookies → pinterest.com")
print("3. Look for these cookies and copy their VALUE:\n")

print("   _b              (main session ID)")
print("   _auth           (auth token)")
print("   _pinterest_sess (session)")
print("   csrftoken       (CSRF token)\n")

print("=" * 80)
print("PASTE YOUR COOKIES")
print("=" * 80 + "\n")

cookies = {}

print("Copy-paste each cookie as: name=value\n")
print("Examples:")
print("  _b=ABC123def456XYZ789...")
print("  _auth=xyz789...")
print("\nLeave blank and press Enter twice when done.\n")

blank_count = 0
while blank_count < 2:
    cookie_input = input("Cookie: ").strip()

    if not cookie_input:
        blank_count += 1
        continue

    blank_count = 0

    if "=" in cookie_input:
        name, value = cookie_input.split("=", 1)
        cookies[name.strip()] = value.strip()
        print(f"   ✓ Saved: {name.strip()}\n")
    else:
        print("❌ Invalid format. Use: name=value\n")

if not cookies:
    print("\n❌ No cookies saved. Exiting.")
    exit(1)

print("\n" + "=" * 80)
print(f"✅ SAVED {len(cookies)} COOKIES")
print("=" * 80 + "\n")

for name, value in cookies.items():
    preview = value[:30] + "..." if len(value) > 30 else value
    print(f"  {name:20} = {preview}")

# Create base64 secret
cookies_json = json.dumps(cookies)
cookies_b64 = base64.b64encode(cookies_json.encode('utf-8')).decode('utf-8')

print("\n" + "=" * 80)
print("GITHUB ACTIONS SECRET")
print("=" * 80 + "\n")

print("SECRET NAME: PINTEREST_COOKIES_B64\n")
print("SECRET VALUE (copy entire string below):\n")
print(cookies_b64)
print("\n")

# Save to file
output_file = Path(__file__).parent / ".pinterest_cookies_b64"
output_file.write_text(cookies_b64, encoding='utf-8')

print("=" * 80)
print("NEXT STEPS")
print("=" * 80 + "\n")

print("1. Copy the SECRET VALUE above (the long base64 string)")
print("\n2. Go to GitHub:")
print("   https://github.com/YOUR_USERNAME/meeeshop-pinterest/settings/secrets/actions")
print("\n3. Click 'New repository secret'")
print("   • Name: PINTEREST_COOKIES_B64")
print("   • Value: (paste the long string above)")
print("   • Click 'Add secret'")
print("\n4. Your workflow will now authenticate! 🎉\n")

print(f"Also saved to: {output_file}\n")
