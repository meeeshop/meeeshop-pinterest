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

import requests
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

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # exponential backoff multiplier


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

    def _try_load_cookies_from_github_secret(self, force_fresh: bool = False) -> bool:
        """
        Try to load Pinterest cookies from GitHub Actions secret (base64 encoded).
        This is the most reliable authentication method for CI/CD.
        Falls back to email/password if cookies are stale.

        Args:
            force_fresh: If True, skip cookies and force email/password auth

        Returns:
            bool: True if cookies loaded and session valid, False otherwise
        """
        if force_fresh:
            logger.info("Forcing fresh authentication (skipping stale cookies)")
            return False

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
            try:
                boards = self.client.boards()
                if boards:
                    logger.info(f"✓ Authenticated via GitHub secret. Found {len(boards)} boards.")
                    self.authenticated = True
                    return True
            except Exception as board_error:
                logger.warning(f"Boards test failed with GitHub secret: {board_error}")
                return False

            logger.warning("Cookies loaded but no boards returned. Session may be invalid.")
            return False

        except Exception as e:
            logger.warning(f"Failed to load cookies from GitHub secret: {e}")
            return False

    def _try_load_cookies_from_file(self) -> bool:
        """
        Try to load Pinterest cookies from local file (for testing).
        Clears stale cookies before attempting to load fresh ones.

        Returns:
            bool: True if cookies loaded and session valid, False otherwise
        """
        if not COOKIES_FILE.exists():
            logger.debug(f"Cookies file not found: {COOKIES_FILE}")
            return False

        try:
            cookies_size = COOKIES_FILE.stat().st_size
            if cookies_size == 0:
                logger.warning(f"Cookies file is empty, clearing stale session data")
                COOKIES_FILE.unlink(missing_ok=True)
                return False

            logger.info(f"Loading Pinterest session from file: {COOKIES_FILE}")
            cookies_json = COOKIES_FILE.read_text(encoding='utf-8-sig').strip()

            if not cookies_json:
                logger.warning("Cookies file is empty, clearing")
                COOKIES_FILE.unlink(missing_ok=True)
                return False

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
            try:
                boards = self.client.boards()
                if boards:
                    logger.info(f"✓ Authenticated via saved cookies. Found {len(boards)} boards.")
                    self.authenticated = True
                    return True
            except Exception as board_error:
                logger.warning(f"Boards test failed with saved cookies: {board_error}")
                return False

            logger.warning("Cookies loaded but no boards returned. Session may be invalid.")
            return False

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse cookies file (corrupted): {e}")
            logger.info("Clearing corrupted cookies file")
            COOKIES_FILE.unlink(missing_ok=True)
            return False
        except Exception as e:
            logger.warning(f"Failed to load cookies from file: {e}")
            return False

    def login(self, force_fresh: bool = False) -> bool:
        """
        Authenticate with Pinterest using multiple fallback methods:
        1. GitHub Actions secret with saved cookies (most reliable for CI)
        2. Local saved cookies file (for testing/development)
        3. Email/password login (fallback, less reliable in CI)

        Args:
            force_fresh: If True, skip cookies and force email/password authentication

        Returns:
            bool: True if authentication successful, False otherwise
        """
        try:
            self.username = os.getenv('PINTEREST_USERNAME', 'meeeshop')

            if not force_fresh:
                # Method 1: Try GitHub Actions secret (saved cookies)
                if self._try_load_cookies_from_github_secret():
                    return True

                # Method 2: Try local cookies file
                if self._try_load_cookies_from_file():
                    return True

            # Method 3: Fall back to email/password login
            logger.info("Attempting email/password login...")

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

    def _get_raw_session(self) -> requests.Session:
        """Return the underlying requests session from py3-pinterest client."""
        if hasattr(self.client, 'http') and isinstance(self.client.http, requests.Session):
            return self.client.http
        if hasattr(self.client, 'session') and isinstance(self.client.session, requests.Session):
            return self.client.session
        raise RuntimeError("Cannot access authenticated session from Pinterest client")

    def _api_post(self, url: str, data: Dict, retry_count: int = 0, session_retry: bool = False) -> requests.Response:
        """Make authenticated POST request to Pinterest API with retry logic."""
        session = self._get_raw_session()
        headers = {
            'Referer': 'https://www.pinterest.com/',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        csrftoken = session.cookies.get('csrftoken')
        if csrftoken:
            headers['X-CSRFToken'] = csrftoken

        from urllib.parse import urlencode
        post_data = urlencode(data)

        try:
            response = session.post(url, data=post_data, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            # Log response body for debugging
            try:
                error_body = e.response.text[:500]
            except:
                error_body = "No response body"

            # 401/403: Session expired, try fresh login
            if e.response.status_code in (401, 403) and not session_retry:
                logger.warning(f"Session invalid (HTTP {e.response.status_code}), response: {error_body}")
                logger.info("Attempting fresh authentication...")
                if self.login(force_fresh=True):
                    logger.info("Fresh authentication successful, retrying API call...")
                    return self._api_post(url, data, retry_count=0, session_retry=True)
                else:
                    logger.error("Fresh authentication failed")
                    raise
            # 500: Transient error, retry with backoff
            elif e.response.status_code == 500 and retry_count < MAX_RETRIES:
                wait_time = (RETRY_BACKOFF ** retry_count)
                logger.warning(f"Pinterest 500 error (attempt {retry_count + 1}/{MAX_RETRIES}), response: {error_body}, retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self._api_post(url, data, retry_count + 1, session_retry=session_retry)
            else:
                logger.error(f"API call failed (HTTP {e.response.status_code}), response: {error_body}")
            raise

    def create_pin(
        self,
        image_path: str,
        title: str,
        description: str,
        board_id: str,
        url: Optional[str] = None,
        alt_text: Optional[str] = None,
        section_id: Optional[str] = None,
        retry_count: int = 0,
    ) -> Tuple[bool, Optional[str]]:
        """Create a pin using py3-pinterest's built-in upload_pin method."""
        if not self.authenticated:
            logger.error("Not authenticated. Call login() first.")
            return False, "Not authenticated"

        image_file = Path(image_path)
        if not image_file.exists():
            error_msg = f"Image file not found: {image_path}"
            logger.error(error_msg)
            return False, error_msg

        logger.info(f"Creating pin: {title} (attempt {retry_count + 1})")

        try:
            self._rate_limit()
            result = self.client.upload_pin(
                image_file=str(image_file),
                board_id=board_id,
                description=description,
                title=title,
                link=url or '',
                alt_text=alt_text or '',
            )

            if result:
                pin_id = result.get('id') if isinstance(result, dict) else str(result)
                logger.info(f"Pin created successfully. ID: {pin_id}")
                return True, pin_id
            else:
                error_msg = "upload_pin returned None/False"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Failed to create pin: {str(e)}"
            logger.error(error_msg)
            if retry_count < MAX_RETRIES:
                wait_time = (RETRY_BACKOFF ** retry_count)
                logger.warning(f"Retrying pin creation in {wait_time}s (attempt {retry_count + 1}/{MAX_RETRIES})")
                time.sleep(wait_time)
                return self.create_pin(
                    image_path=image_path,
                    title=title,
                    description=description,
                    board_id=board_id,
                    url=url,
                    alt_text=alt_text,
                    section_id=section_id,
                    retry_count=retry_count + 1
                )
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
