"""
Pinterest client using py3-pinterest library for direct API communication.
Replaces Selenium WebDriver automation with HTTP-based API calls.
"""

import os
import time
import json
import base64
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import logging

from py3pin.Pinterest import Pinterest
from dotenv import load_dotenv

from content_generator import generate_content_package
from credentials_manager import CredentialsManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

COOKIES_FILE = Path(__file__).parent / ".pinterest_cookies_b64"


class PinterestClient:
    """
    Pinterest API client using py3-pinterest for direct HTTP communication.
    Eliminates Selenium WebDriver dependency for more reliable automation.
    Prioritizes saved session cookies over email/password auth (more reliable in CI).
    """

    def __init__(self):
        """Initialize Pinterest client with credentials from environment/credentials_manager."""
        self.client = None
        self.email = None
        self.password = None
        self.username = None
        self.authenticated = False
        self.rate_limit_delay = 2  # seconds between API calls
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _try_load_cookies_from_github_secret(self) -> bool:
        """
        Try to load Pinterest cookies from GitHub Actions secret (base64 encoded).
        This is the most reliable authentication method for CI/CD.

        Returns:
            bool: True if cookies loaded and session valid, False otherwise
        """
        cookies_b64 = os.getenv('PINTEREST_COOKIES_B64')
        if not cookies_b64:
            logger.debug("No PINTEREST_COOKIES_B64 secret found")
            return False

        try:
            logger.info("Loading Pinterest session from GitHub secret...")
            cookies_b64 = cookies_b64.strip()
            cookies_json = base64.b64decode(cookies_b64).decode('utf-8-sig')
            cookies_dict = json.loads(cookies_json)

            logger.debug(f"Loaded {len(cookies_dict)} cookies from secret")

            # Create Pinterest client and inject cookies into session
            self.client = Pinterest()
            if hasattr(self.client, 'session') and cookies_dict:
                for key, value in cookies_dict.items():
                    self.client.session.cookies.set(key, value)
                logger.debug(f"Injected {len(cookies_dict)} cookies into session")

            # Test if session is valid
            self._rate_limit()
            boards = self.client.boards()
            if boards:
                logger.info(f"✓ Authenticated via GitHub secret. Found {len(boards)} boards.")
                self.authenticated = True
                return True
            else:
                logger.warning("Cookies loaded but no boards returned. Session may be invalid.")
                return False

        except Exception as e:
            logger.warning(f"Failed to load cookies from GitHub secret: {e}")
            return False

    def _try_load_cookies_from_file(self) -> bool:
        """
        Try to load Pinterest cookies from local file (for testing).

        Returns:
            bool: True if cookies loaded and session valid, False otherwise
        """
        if not COOKIES_FILE.exists():
            logger.debug(f"Cookies file not found: {COOKIES_FILE}")
            return False

        try:
            logger.info(f"Loading Pinterest session from file: {COOKIES_FILE}")
            cookies_json = COOKIES_FILE.read_text(encoding='utf-8-sig').strip()
            cookies_dict = json.loads(cookies_json)

            logger.debug(f"Loaded {len(cookies_dict)} cookies from file")

            # Create Pinterest client and inject cookies into session
            self.client = Pinterest()
            if hasattr(self.client, 'session') and cookies_dict:
                for key, value in cookies_dict.items():
                    self.client.session.cookies.set(key, value)
                logger.debug(f"Injected {len(cookies_dict)} cookies into session")

            # Test if session is valid
            self._rate_limit()
            boards = self.client.boards()
            if boards:
                logger.info(f"✓ Authenticated via saved cookies. Found {len(boards)} boards.")
                self.authenticated = True
                return True
            else:
                logger.warning("Cookies loaded but no boards returned. Session may be invalid.")
                return False

        except Exception as e:
            logger.warning(f"Failed to load cookies from file: {e}")
            return False

    def login(self) -> bool:
        """
        Authenticate with Pinterest using multiple fallback methods:
        1. GitHub Actions secret with saved cookies (most reliable for CI)
        2. Local saved cookies file (for testing/development)
        3. Email/password login (fallback, less reliable in CI)

        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            self.username = os.getenv('PINTEREST_USERNAME', 'meeeshop')

            # Method 1: Try GitHub Actions secret (saved cookies)
            if self._try_load_cookies_from_github_secret():
                return True

            # Method 2: Try local cookies file
            if self._try_load_cookies_from_file():
                return True

            # Method 3: Fall back to email/password login
            logger.info("No saved cookies available. Attempting email/password login...")

            creds = CredentialsManager.get_from_env()
            if not creds:
                logger.error("No credentials found in environment")
                return False

            self.email = creds.get('email')
            self.password = creds.get('password')

            if not (self.email and self.password):
                logger.error("Pinterest credentials (email/password) not found")
                return False

            logger.info(f"Logging in with email: {self.email}")
            self.client = Pinterest(
                email=self.email,
                password=self.password,
                username=self.username
            )

            # Test authentication by attempting to fetch boards
            self._rate_limit()
            boards = self.client.boards()
            if boards:
                logger.info(f"✓ Successfully authenticated. Found {len(boards)} boards.")
                self.authenticated = True
                return True
            else:
                logger.warning("Authentication succeeded but no boards found")
                self.authenticated = True
                return True

        except Exception as e:
            logger.error(f"Login failed: {type(e).__name__}: {e}")
            return False

    def fetch_boards(self) -> List[Dict[str, str]]:
        """
        Fetch user's Pinterest boards using API.

        Returns:
            List[Dict]: List of board info dicts with 'id', 'name', 'url' keys
        """
        if not self.authenticated:
            logger.error("Not authenticated. Call login() first.")
            return []

        try:
            self._rate_limit()
            boards = self.client.boards()

            board_list = []
            for board in boards:
                # py3-pinterest board object has attributes: name, url, board_id
                board_info = {
                    'id': board.get('id') or board.get('board_id'),
                    'name': board.get('name'),
                    'url': board.get('url')
                }
                board_list.append(board_info)
                logger.info(f"Board: {board_info['name']} (ID: {board_info['id']})")

            return board_list

        except Exception as e:
            logger.error(f"Failed to fetch boards: {e}")
            return []

    def create_pin(
        self,
        image_path: str,
        title: str,
        description: str,
        board_id: str,
        url: Optional[str] = None,
        alt_text: Optional[str] = None,
        section_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a pin on Pinterest using direct API call.

        Args:
            image_path: Path to image file
            title: Pin title
            description: Pin description
            board_id: Target board ID
            url: Optional URL for pin (clickthrough)
            alt_text: Optional alt text for accessibility
            section_id: Optional section within board

        Returns:
            Tuple[bool, Optional[str]]: (success, pin_id or error_message)
        """
        if not self.authenticated:
            logger.error("Not authenticated. Call login() first.")
            return False, "Not authenticated"

        # Validate session before pin creation
        try:
            self._rate_limit()
            self.client.boards()
            logger.debug("Session still valid before pin creation")
        except Exception as e:
            logger.warning(f"Session lost before pin creation: {e}. Re-authenticating...")
            if not self.login():
                return False, "Failed to re-authenticate"

        try:
            # Validate image file exists
            image_file = Path(image_path)
            if not image_file.exists():
                error_msg = f"Image file not found: {image_path}"
                logger.error(error_msg)
                return False, error_msg

            # Rate limit before API call
            self._rate_limit()

            # Build pin metadata
            pin_data = {
                'description': description,
                'title': title,
            }

            if url:
                pin_data['link'] = url

            # Note: py3-pinterest may not support alt_text directly in upload_pin()
            # If needed, alt_text should be included in description or handled separately
            if alt_text:
                pin_data['alt_text'] = alt_text

            # Create pin via API
            logger.info(f"Creating pin: {title}")
            pin_result = self.client.upload_pin(
                board_id=board_id,
                image_file=str(image_file),
                description=description,
                title=title,
                link=url,
                section_id=section_id
            )

            if pin_result:
                pin_id = pin_result.get('id') or pin_result
                logger.info(f"Pin created successfully. ID: {pin_id}")
                return True, str(pin_id)
            else:
                error_msg = f"Pin creation returned empty or unsuccessful result: {pin_result}"
                logger.warning(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Failed to create pin: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def get_board_by_name(self, board_name: str) -> Optional[Dict[str, str]]:
        """
        Find a board by name.

        Args:
            board_name: Name of the board to find

        Returns:
            Dict with board info or None if not found
        """
        boards = self.fetch_boards()
        for board in boards:
            if board['name'].lower() == board_name.lower():
                return board

        logger.warning(f"Board not found: {board_name}")
        return None


def main():
    """Example usage of PinterestClient."""
    client = PinterestClient()

    # Login
    if not client.login():
        print("Login failed")
        return

    # Fetch boards
    boards = client.fetch_boards()
    if not boards:
        print("No boards found")
        return

    print(f"\nFound {len(boards)} boards:")
    for board in boards:
        print(f"  - {board['name']} (ID: {board['id']})")


if __name__ == "__main__":
    main()
