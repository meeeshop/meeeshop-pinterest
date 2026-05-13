"""
credentials_manager.py — Secure Pinterest credential handling
Supports: env vars, .env file, Chrome cookies, stored tokens
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
import pickle

logger = logging.getLogger(__name__)

COOKIES_FILE = Path(__file__).parent / ".pinterest_cookies.pkl"
SESSION_FILE = Path(__file__).parent / ".pinterest_session"


class CredentialsManager:
    """Manage Pinterest credentials securely"""

    @staticmethod
    def load_env():
        """Load .env file into environment"""
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"'))

    @staticmethod
    def get_from_env() -> Optional[Dict[str, str]]:
        """Get credentials from environment variables"""
        CredentialsManager.load_env()

        email = os.getenv("PINTEREST_EMAIL")
        password = os.getenv("PINTEREST_PASSWORD")

        if email and password:
            logger.info("✓ Credentials loaded from .env")
            return {"email": email, "password": password}

        return None

    @staticmethod
    def save_cookies(driver: webdriver.Chrome) -> bool:
        """Save Pinterest session cookies to file"""
        try:
            cookies = driver.get_cookies()
            pickle.dump(cookies, COOKIES_FILE.open("wb"))
            logger.info(f"✓ Cookies saved: {COOKIES_FILE}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False

    @staticmethod
    def load_cookies(driver: webdriver.Chrome) -> bool:
        """Load Pinterest session cookies from file"""
        if not COOKIES_FILE.exists():
            return False

        try:
            driver.get("https://pinterest.com")  # Must visit domain first
            cookies = pickle.load(COOKIES_FILE.open("rb"))
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception:
                    pass
            logger.info("✓ Cookies loaded from file")
            return True
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return False

    @staticmethod
    def extract_session_token(driver: webdriver.Chrome) -> Optional[str]:
        """Extract Pinterest session token from cookies"""
        try:
            cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            # Pinterest uses '_pinterest_sess' or similar
            token = cookies.get("_pinterest_sess") or cookies.get("_auth") or cookies.get("_b")
            if token:
                logger.info(f"✓ Session token found: {token[:20]}...")
                return token
            return None
        except Exception as e:
            logger.error(f"Failed to extract session token: {e}")
            return None

    @staticmethod
    def save_session_token(token: str) -> bool:
        """Save session token for reuse"""
        try:
            SESSION_FILE.write_text(token, encoding="utf-8")
            logger.info(f"✓ Session token saved")
            return True
        except Exception as e:
            logger.error(f"Failed to save session token: {e}")
            return False

    @staticmethod
    def load_session_token() -> Optional[str]:
        """Load saved session token"""
        if SESSION_FILE.exists():
            try:
                token = SESSION_FILE.read_text(encoding="utf-8").strip()
                logger.info("✓ Session token loaded from file")
                return token
            except Exception as e:
                logger.error(f"Failed to load session token: {e}")
        return None


class ChromeProfileManager:
    """Use Chrome user profile to avoid login"""

    @staticmethod
    def get_user_profile_path() -> Optional[str]:
        """Find Chrome profile already logged into Pinterest"""
        import platform
        import subprocess

        system = platform.system()

        try:
            if system == "Windows":
                # Check if Chrome is running with existing profile
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                    capture_output=True,
                    text=True,
                )
                if "chrome.exe" in result.stdout:
                    logger.warning("Chrome is running. Close it before using Chrome profile.")
                    return None

                # Default Chrome profile path
                profile_path = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default"

            elif system == "Darwin":  # macOS
                profile_path = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default"

            else:  # Linux
                profile_path = Path.home() / ".config" / "google-chrome" / "Default"

            if profile_path.exists():
                logger.info(f"✓ Chrome profile found: {profile_path}")
                return str(profile_path)

        except Exception as e:
            logger.error(f"Failed to find Chrome profile: {e}")

        return None

    @staticmethod
    def create_options_with_profile(profile_path: str) -> webdriver.ChromeOptions:
        """Create Chrome options with existing profile"""
        options = webdriver.ChromeOptions()
        options.add_argument(f"user-data-dir={profile_path}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")
        return options


def interactive_login_and_save(email: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Interactive login with option to save session for future use

    Steps:
    1. Open browser
    2. User logs in manually (no password entry required)
    3. Script saves cookies
    4. Future runs use cookies (no re-login needed)
    """
    from selenium import webdriver
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    logger.info("Opening Pinterest for manual login...")

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://pinterest.com/login/")

        # Wait for user to login manually
        logger.info("📌 Please log in to Pinterest manually in the browser...")
        logger.info("⏳ Waiting for login (max 5 minutes)...")

        # Wait for home feed to appear (indicates successful login)
        WebDriverWait(driver, 300).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='homefeed']"))
        )

        logger.info("✓ Login detected! Saving cookies...")

        # Save cookies for future use
        CredentialsManager.save_cookies(driver)

        # Extract and save token
        token = CredentialsManager.extract_session_token(driver)
        if token:
            CredentialsManager.save_session_token(token)

        logger.info("✓ Session saved! Next time will use saved cookies.")

        # Get email if available
        try:
            account_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label*='account' i]")
            account_btn.click()
            # Could extract email here, but risky
        except Exception:
            pass

        return {"email": email or "saved_session", "use_cookies": True}

    except Exception as e:
        logger.error(f"Manual login failed: {e}")
        return None

    finally:
        driver.quit()


def main():
    """Demo: Different login methods"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("\n📌 Pinterest Credentials — Available Methods:\n")

    # Method 1: Environment variables
    print("1️⃣  FROM .env FILE (Recommended)")
    creds = CredentialsManager.get_from_env()
    if creds:
        print(f"   ✓ Found: {creds['email']}")
    else:
        print("   ✗ Not found (copy .env.example to .env)")

    # Method 2: Chrome cookies
    print("\n2️⃣  FROM SAVED COOKIES (No re-login needed)")
    if COOKIES_FILE.exists():
        print(f"   ✓ Found: {COOKIES_FILE}")
    else:
        print("   ✗ Not found (run interactive login first)")

    # Method 3: Chrome profile
    print("\n3️⃣  FROM CHROME PROFILE (Browser already logged in)")
    profile = ChromeProfileManager.get_user_profile_path()
    if profile:
        print(f"   ✓ Found: {profile}")
    else:
        print("   ✗ Not found or Chrome is running")

    # Method 4: Manual/Interactive
    print("\n4️⃣  INTERACTIVE LOGIN (Manual in browser)")
    print("   Use: interactive_login_and_save()")
    print("   (Browser opens, you log in manually, cookies saved)")

    print("\n💡 RECOMMENDED FLOW:\n")
    print("   First time:")
    print("     python -c \"from credentials_manager import interactive_login_and_save; interactive_login_and_save()\"")
    print("   After cookies saved:")
    print("     python pinterest_daily.py  # Uses saved cookies, no password needed!")


if __name__ == "__main__":
    main()
