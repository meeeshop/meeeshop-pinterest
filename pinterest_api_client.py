"""
pinterest_api_client_fixed.py — Pinterest automation using py3-pinterest library
Fixes the 401 Unauthorized issue by properly managing session cookies.
"""

import logging
import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

try:
    from py3pin.Pinterest import Pinterest
except ImportError:
    logger.error("py3-pinterest not installed. Run: pip install py3-pinterest")
    Pinterest = None


class PinterestAPIClient:
    """Pinterest automation using py3-pinterest (no browser needed)"""

    def __init__(self, email: str = None, password: str = None, username: str = None):
        """Initialize Pinterest client with credentials from .env or parameters"""

        # Load .env if not already loaded
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)

        self.email = email or os.getenv("PINTEREST_EMAIL")
        self.password = password or os.getenv("PINTEREST_PASSWORD")
        self.username = username or os.getenv("PINTEREST_USERNAME", "meeeshop")

        self.client = None
        self.logged_in = False
        self.boards_cache = {}
        self.cookie_file = Path(__file__).parent / ".pinterest_cookies"

        if not self.email or not self.password:
            logger.error("Missing PINTEREST_EMAIL or PINTEREST_PASSWORD in .env")
            return

        if Pinterest is None:
            logger.error("py3-pinterest library not available")
            return

        try:
            # Initialize py3-pinterest client
            cred_root = Path(__file__).parent / ".pinterest_creds"
            cred_root.mkdir(exist_ok=True)

            self.client = Pinterest(
                email=self.email,
                password=self.password,
                username=self.username,
                cred_root=str(cred_root)
            )
            logger.info(f"✓ Pinterest client initialized for {self.email}")
        except Exception as e:
            logger.error(f"Failed to initialize Pinterest client: {e}")
            self.client = None

    def _load_cookies_from_file(self):
        """Load cookies from .pinterest_cookies file if exists."""
        if self.cookie_file.exists():
            try:
                with open(self.cookie_file, 'r') as f:
                    lines = f.readlines()
                cookies = {}
                for line in lines:
                    if '=' in line and not line.startswith('updated'):
                        key, value = line.strip().split('=', 1)
                        cookies[key] = value
                logger.info(f"✓ Loaded {len(cookies)} cookies from file")
                return cookies
            except Exception as e:
                logger.warning(f"Could not load cookies from file: {e}")
        return None

    def _save_cookies_to_file(self, cookies):
        """Save cookies to .pinterest_cookies file."""
        try:
            with open(self.cookie_file, 'w') as f:
                for key, value in cookies.items():
                    f.write(f"{key}={value}\n")
                f.write(f"updated={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
            logger.info(f"✓ Saved cookies to {self.cookie_file}")
        except Exception as e:
            logger.warning(f"Could not save cookies: {e}")

    def login(self) -> bool:
        """Login to Pinterest using Chrome/Selenium to get proper cookies"""
        if not self.client:
            logger.error("Client not initialized")
            return False

        try:
            logger.info("🔑 Logging into Pinterest with Chrome...")
            # This uses Selenium to log in and sets cookies properly
            self.client.login(headless=True, wait_time=20)
            self.logged_in = True

            # Extract cookies from the session
            cookies = self.client.http.cookies.get_dict()
            logger.info(f"✓ Successfully logged in. Got {len(cookies)} cookies")

            # Save cookies for future use
            self._save_cookies_to_file(cookies)

            # Also persist via registry
            self.client.registry.update_all(cookies)

            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            self.logged_in = False
            return False

    def fetch_boards(self) -> Dict[str, str]:
        """Fetch all boards for the user. Returns {board_name: board_id}"""
        if not self.logged_in:
            logger.warning("Not logged in, skipping board fetch")
            return {}

        try:
            logger.info("📋 Fetching boards...")
            boards = self.client.boards_all()

            if not boards:
                logger.warning("No boards found")
                return {}

            board_map = {}
            for board in boards:
                board_name = board.get("name", "Unknown")
                board_id = board.get("id", "")
                board_map[board_name] = board_id
                logger.info(f"  ✓ {board_name} (ID: {board_id})")

            self.boards_cache = board_map
            return board_map
        except Exception as e:
            logger.error(f"Failed to fetch boards: {e}")
            return {}

    def create_pin(
        self,
        image_or_video_path: str,
        title: str,
        description: str = "",
        board_name: str = None,
        url: str = None,
        alt_text: str = None,
    ) -> bool:
        """Create a pin on Pinterest from local file"""
        if not self.logged_in:
            logger.error("Not logged in")
            return False

        if not self.client:
            logger.error("Client not initialized")
            return False

        try:
            logger.info(f"📌 Creating pin: '{title}'")

            # Get board ID if board name is provided
            board_id = None
            if board_name:
                if not self.boards_cache:
                    self.fetch_boards()
                board_id = self.boards_cache.get(board_name)
                if not board_id:
                    logger.warning(f"Board '{board_name}' not found, using first available")
                    if self.boards_cache:
                        board_id = list(self.boards_cache.values())[0]
                    else:
                        logger.warning(f"No boards available")
                        return False

            # Determine if it's a video or image
            is_video = image_or_video_path.lower().endswith(('.mp4', '.mov', '.avi', '.webm'))

            # Create pin using upload_pin or upload_video_pin
            if is_video:
                logger.info(f"  📹 Uploading video pin...")
                result = self.client.upload_video_pin(
                    video_file=image_or_video_path,
                    board_id=board_id,
                    title=title,
                    description=description,
                    link=url,
                    alt_text=alt_text,
                )
            else:
                logger.info(f"  🖼️ Uploading image pin...")
                result = self.client.upload_pin(
                    image_file=image_or_video_path,
                    board_id=board_id,
                    description=description,
                    title=title,
                    link=url,
                    alt_text=alt_text,
                )

            if result:
                logger.info(f"✅ Pin created successfully!")
                return True
            else:
                logger.error(f"Pin creation returned None/False. Result: {result}")
                return False

        except Exception as e:
            logger.error(f"Failed to create pin: {e}")
            return False

    def create_pin_from_url(
        self,
        image_url: str,
        title: str,
        description: str = "",
        board_name: str = None,
        url: str = None,
    ) -> bool:
        """Create a pin from an image URL (downloads and uploads)"""
        if not self.logged_in:
            logger.error("Not logged in")
            return False

        try:
            import requests
            import tempfile

            logger.info(f"📌 Creating pin from URL: '{title}'")

            # Download image
            logger.info(f"  Downloading image...")
            resp = requests.get(image_url, timeout=10)
            resp.raise_for_status()

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(resp.content)
                temp_path = f.name

            try:
                # Create pin from local file
                success = self.create_pin(
                    image_or_video_path=temp_path,
                    title=title,
                    description=description,
                    board_name=board_name,
                    url=url,
                )
                return success
            finally:
                # Clean up temp file
                Path(temp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Failed to create pin from URL: {e}")
            return False

    def close(self):
        """Close client connection"""
        if self.client:
            try:
                self.client = None
                logger.info("Pinterest client closed")
            except Exception as e:
                logger.warning(f"Error closing client: {e}")


def main():
    """Test Pinterest API client"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Initialize client
    pinterest = PinterestAPIClient()

    try:
        # Login
        if not pinterest.login():
            logger.error("Failed to login")
            return False

        # Fetch boards
        boards = pinterest.fetch_boards()
        logger.info(f"Found {len(boards)} boards")

        # Test pin creation (use a real image URL)
        test_image_url = "https://cdn.shopify.com/s/files/1/0605/3992/8747/files/21227_2_2e4bed96-5e45-42e5-8f73-c33c10c02d00.jpg"

        success = pinterest.create_pin_from_url(
            image_url=test_image_url,
            title="Test Pin from py3-pinterest",
            description="Testing the fixed py3-pinterest client",
            board_name="Saved",  # Use default board if custom not available
            url="https://us.meeeshop.com",
        )

        if success:
            logger.info("✅ Test pin created successfully!")
        else:
            logger.error("❌ Test pin creation failed")

        return success

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False

    finally:
        pinterest.close()


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
