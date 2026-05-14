#!/usr/bin/env python3
"""
Extract Pinterest cookies from Chrome browser and prepare for GitHub Actions.
Run this while you're logged into Pinterest in Chrome.
"""

import json
import base64
import sys
import platform
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_chrome_cookies():
    """Extract Pinterest cookies from Chrome browser."""

    # Determine Chrome profile path based on OS
    if platform.system() == "Windows":
        chrome_path = Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Cookies"
    elif platform.system() == "Darwin":  # macOS
        chrome_path = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
    else:  # Linux
        chrome_path = Path.home() / ".config/google-chrome/Default/Cookies"

    if not chrome_path.exists():
        print(f"❌ Chrome cookies database not found at: {chrome_path}")
        print("\n⚠️  Make sure:")
        print("   1. Chrome is CLOSED (close all Chrome windows)")
        print("   2. You're on the correct OS/user account")
        return None

    try:
        # Need browser_cookie3 or similar to read Chrome's encrypted cookies
        print("⚠️  Attempting to read Chrome cookies...")
        print("   This requires the Chrome profile to be closed.\n")

        try:
            import browser_cookie3
        except ImportError:
            print("❌ browser_cookie3 not installed.")
            print("\nInstall it with:")
            print("   pip install browser-cookie3\n")
            return None

        # Get cookies for pinterest.com
        cj = browser_cookie3.chrome(domain_name="pinterest.com")
        cookies = {}
        for cookie in cj:
            cookies[cookie.name] = cookie.value

        return cookies

    except Exception as e:
        print(f"❌ Error reading Chrome cookies: {e}\n")
        return None


def manual_method():
    """Show manual method to copy cookies."""
    print("\n" + "=" * 80)
    print("MANUAL METHOD (Recommended - Easier!)")
    print("=" * 80 + "\n")

    print("📌 Step 1: Open Chrome DevTools")
    print("   1. Go to https://pinterest.com")
    print("   2. Press F12 or Ctrl+Shift+I to open DevTools")
    print("   3. Go to 'Application' tab (top menu)")
    print("   4. Click 'Cookies' → 'pinterest.com' (left sidebar)\n")

    print("📌 Step 2: Copy these cookies:")
    print("   Look for these cookie names and copy their VALUES:\n")

    important_cookies = [
        ("_b", "Main Pinterest session ID"),
        ("_auth", "Authentication token"),
        ("_pinterest_sess", "Session cookie"),
        ("csrftoken", "CSRF protection token"),
    ]

    for cookie_name, description in important_cookies:
        print(f"   • {cookie_name:25} ({description})")
        print(f"     ↳ Right-click on row → Copy 'Value'\n")

    print("📌 Step 3: Paste below (one per line, leave blank to skip):")
    print("   Format: name=value\n")

    cookies = {}
    while True:
        user_input = input("Cookie (or press Enter to finish): ").strip()
        if not user_input:
            break
        if "=" in user_input:
            name, value = user_input.split("=", 1)
            cookies[name.strip()] = value.strip()
        else:
            print("❌ Invalid format. Use: name=value")

    return cookies if cookies else None


def create_github_secret(cookies):
    """Create base64-encoded GitHub secret."""
    cookies_json = json.dumps(cookies, indent=2)
    cookies_b64 = base64.b64encode(cookies_json.encode('utf-8')).decode('utf-8')

    print("\n" + "=" * 80)
    print("✅ GITHUB SECRET")
    print("=" * 80 + "\n")

    print("Copy this entire base64 string:\n")
    print(cookies_b64)
    print("\n")

    print("=" * 80)
    print("📋 NEXT STEPS")
    print("=" * 80 + "\n")

    print("1. Go to GitHub repository settings:")
    print("   https://github.com/YOUR_USERNAME/meeeshop-pinterest/settings/secrets/actions\n")

    print("2. Click 'New repository secret'\n")

    print("3. Fill in:")
    print("   Secret name:  PINTEREST_COOKIES_B64")
    print("   Secret value: (paste the base64 string above)\n")

    print("4. Click 'Add secret'\n")

    print("5. Done! GitHub Actions will now use your Pinterest session! 🎉\n")

    # Save to file for reference
    output_file = Path(__file__).parent / ".pinterest_cookies_b64"
    output_file.write_text(cookies_b64, encoding='utf-8')
    print(f"ℹ️  Also saved to: {output_file}\n")


def main():
    print("\n" + "=" * 80)
    print("EXTRACT PINTEREST COOKIES FOR GITHUB ACTIONS")
    print("=" * 80 + "\n")

    print("Choose method:\n")
    print("1. Automatic (read from Chrome) - requires: pip install browser-cookie3")
    print("2. Manual (copy-paste from DevTools) - easiest!\n")

    choice = input("Choose 1 or 2 (default 2): ").strip() or "2"

    cookies = None

    if choice == "1":
        print("\n⚠️  IMPORTANT: Close all Chrome windows before continuing!\n")
        input("Press Enter once Chrome is closed... ")
        cookies = get_chrome_cookies()
    else:
        cookies = manual_method()

    if not cookies:
        print("❌ No cookies extracted. Exiting.")
        return False

    print(f"\n✅ Extracted {len(cookies)} cookies:")
    for name in cookies.keys():
        print(f"   • {name}")

    create_github_secret(cookies)
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
