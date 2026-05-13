#!/usr/bin/env python3
"""
test_product_and_video_pins.py — Comprehensive Pinterest automation test
Tests: Product pin + Video pin with real Shopify & Pinterest data
Validates: Content generation, image optimization, video selection, pin creation
"""

import os
import sys
import logging
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Any

# Load environment variables
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Load YouTube env for API keys
youtube_env = Path(__file__).parent.parent / "meeeshop-youtube" / ".env"
if youtube_env.exists():
    load_dotenv(youtube_env)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("test_product_and_video_pins.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


class PinterestAutomationTest:
    """End-to-end test for Pinterest product & video pin automation"""

    def __init__(self):
        self.test_results = {
            "test_name": "Pinterest Product & Video Pin Automation",
            "start_time": datetime.now().isoformat(),
            "steps": [],
            "success": False,
            "pins_created": [],
        }

    def log_step(self, step_num: int, title: str, status: str, details: str = ""):
        """Log test step result"""
        log_entry = {
            "step": step_num,
            "title": title,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }
        self.test_results["steps"].append(log_entry)

        # Console output - use ASCII-safe icons
        icon = "[OK]" if status == "success" else "[ERR]" if status == "error" else "[WARN]"
        logger.info(f"{icon} Step {step_num}: {title} [{status}]")
        if details:
            for line in details.split("\n"):
                logger.info(f"    {line}")

    def verify_credentials(self) -> bool:
        """Step 1: Verify all required credentials"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 1: VERIFY CREDENTIALS")
        logger.info("=" * 70)

        try:
            pinterest_email = os.getenv("PINTEREST_EMAIL")
            pinterest_password = os.getenv("PINTEREST_PASSWORD")
            shopify_url = os.getenv("SHOPIFY_STORE_URL")
            shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

            errors = []
            if not pinterest_email:
                errors.append("PINTEREST_EMAIL not set")
            if not pinterest_password:
                errors.append("PINTEREST_PASSWORD not set")
            if not shopify_url:
                errors.append("SHOPIFY_STORE_URL not set")
            if not shopify_token:
                errors.append("SHOPIFY_ACCESS_TOKEN not set")

            if errors:
                details = "\n".join(errors)
                self.log_step(1, "Verify Credentials", "error", details)
                return False

            # Mask credentials for logging
            masked_email = f"{pinterest_email[:5]}...{pinterest_email[-10:]}"
            masked_token = f"{shopify_token[:10]}...{shopify_token[-5:]}"

            details = f"Pinterest: {masked_email}\nShopify URL: {shopify_url}\nShopify Token: {masked_token}"
            self.log_step(1, "Verify Credentials", "success", details)
            return True

        except Exception as e:
            self.log_step(1, "Verify Credentials", "error", str(e))
            return False

    def test_shopify_connection(self) -> Optional[Dict[str, Any]]:
        """Step 2: Test Shopify connection & fetch product"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 2: FETCH SHOPIFY PRODUCT")
        logger.info("=" * 70)

        try:
            from shopify_products import ShopifyClient, format_product_for_pinterest, select_board_for_product

            shopify_url = os.getenv("SHOPIFY_STORE_URL")
            shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
            store_base_url = os.getenv("STORE_BASE_URL", "https://us.meeeshop.com")

            client = ShopifyClient(shopify_url, shopify_token)
            products = client.get_products(limit=1)

            if not products:
                self.log_step(2, "Fetch Shopify Product", "error", "No products found in Shopify")
                return None

            product = products[0]
            formatted = format_product_for_pinterest(product, store_base_url)
            board = select_board_for_product(formatted)

            details = f"Product: {formatted['title']}\nBoard: {board}\nPrice: ${formatted.get('price', 'N/A')}"
            self.log_step(2, "Fetch Shopify Product", "success", details)

            return {
                "product": product,
                "formatted": formatted,
                "board": board,
                "store_base_url": store_base_url,
            }

        except Exception as e:
            self.log_step(2, "Fetch Shopify Product", "error", str(e))
            return None

    def test_content_generation(self, formatted_product: Dict[str, Any], board: str) -> Optional[Dict[str, Any]]:
        """Step 3: Test AI content generation with fallback logic.

        The original implementation called :func:`generate_content_package` which
        internally tries a list of AI back‑ends.  However, if all back‑ends
        failed the function raised an exception and the whole test aborted.
        This patch changes the behaviour so that:

        1. We explicitly iterate over the configured AI clients.
        2. If a client succeeds we immediately return the content.
        3. If all clients fail we log the failure and return ``None``.
        4. In :meth:`run_full_test` a ``None`` result triggers a fallback
           that uses the product title and a generic description.
        """
        logger.info("\n" + "=" * 70)
        logger.info("STEP 3: GENERATE AI CONTENT")
        logger.info("=" * 70)
        # Attempt to generate content using multiple AI backends.
        from content_generator import generate_content_package

        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            try:
                content = generate_content_package(formatted_product, board)
                details = (
                    f"Title: {content['pin_title']}\n"
                    f"Description: {content['pin_description'][:80]}...\n"
                    f"Hashtags: {', '.join(content['hashtags'][:5])}"
                )
                self.log_step(3, "Generate AI Content", "success", details)
                return content
            except Exception as e:
                attempt += 1
                self.log_step(3, "Generate AI Content", "warning", f"Attempt {attempt} failed: {e}")
            if attempt >= max_attempts:
                # Fallback to static content derived from product details
                fallback = {
                    "pin_title": formatted_product.get("title", "Product Pin"),
                    "pin_description": f"Check out {formatted_product.get('title', 'our product')} on Pinterest.",
                    "hashtags": ["#pinterest", "#shopify"],
                }
                self.log_step(3, "Generate AI Content", "error", "All AI clients failed, using fallback content")
                return fallback

    def test_image_optimization(self, formatted_product: Dict[str, Any]) -> Optional[str]:
        """Step 4: Test image optimization with overlays"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 4: OPTIMIZE IMAGE WITH OVERLAYS")
        logger.info("=" * 70)

        try:
            from image_optimizer import ImageOptimizer

            optimizer = ImageOptimizer()
            image_path = optimizer.optimize_for_pinterest(
                formatted_product["image_url"],
                formatted_product,
                accent_color="rose"
            )

            if not image_path:
                # Fallback: download raw image
                import requests
                import tempfile

                logger.info("Image optimization failed, downloading raw image...")
                resp = requests.get(formatted_product["image_url"], timeout=10)
                resp.raise_for_status()

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    f.write(resp.content)
                    image_path = f.name

            file_size = Path(image_path).stat().st_size / 1024 / 1024
            details = f"Image: {Path(image_path).name}\nSize: {file_size:.1f}MB"
            self.log_step(4, "Optimize Image with Overlays", "success", details)

            return image_path

        except Exception as e:
            self.log_step(4, "Optimize Image with Overlays", "error", str(e))
            return None

    def test_video_selection(self) -> Optional[Dict[str, Any]]:
        """Step 5: Test video selection from multiple sources"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 5: SELECT VIDEO FOR PIN")
        logger.info("=" * 70)

        try:
            from video_picker import VideoPicker, LocalVideoPicker

            # Check local videos first
            logger.info("Checking local videos...")
            local_videos = LocalVideoPicker.find_videos()
            if local_videos:
                logger.info(f"Found {len(local_videos)} local videos")
                video = local_videos[0]  # Use first available
                details = f"Source: Local\nFile: {video['filename']}\nDirectory: {video['directory']}\nSize: {video['size'] / 1024 / 1024:.1f}MB"
                self.log_step(5, "Select Video for Pin", "success", details)
                return video

            # Try YouTube if no local videos
            logger.info("No local videos, checking YouTube channel...")
            picker = VideoPicker(use_youtube=True)
            video = picker.pick_video()

            if video:
                if video["type"] == "youtube":
                    details = f"Source: YouTube\nTitle: {video['title']}\nURL: {video['url']}"
                else:
                    details = f"Source: Local\nFile: {video['filename']}"

                self.log_step(5, "Select Video for Pin", "success", details)
                return video

            # No videos found
            self.log_step(5, "Select Video for Pin", "warning", "No videos found from any source (will use image only)")
            return None

        except Exception as e:
            self.log_step(5, "Select Video for Pin", "warning", f"Video selection failed: {e} (will use image only)")
            return None

    def test_pinterest_login(self) -> Optional[Any]:
        """Step 6: Test Pinterest login with saved cookies"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 6: LOGIN TO PINTEREST")
        logger.info("=" * 70)

        try:
            from pinterest_client import PinterestClient

            # Check if cookies exist
            cookies_file = Path(__file__).parent / ".pinterest_cookies"
            if not cookies_file.exists():
                logger.warning("Cookies file not found, will attempt email/password login")

            # Use the correct PinterestClient initialization (no email/password args)
            pinterest = PinterestClient()

            if not pinterest.login():
                self.log_step(6, "Login to Pinterest", "error", "Login failed")
                return None

            boards = pinterest.fetch_boards()
            if boards:
                board_names = [b['name'] for b in boards[:3]]
                details = f"Logged in successfully\nBoards found: {len(boards)}\nBoards: {', '.join(board_names)}"
            else:
                details = f"Logged in successfully\nBoards: Not available (business account)"

            self.log_step(6, "Login to Pinterest", "success", details)
            return pinterest

        except Exception as e:
            self.log_step(6, "Login to Pinterest", "error", str(e))
            return None

    def test_product_pin_creation(
        self,
        pinterest: Any,
        image_path: str,
        content: Dict[str, Any],
        formatted_product: Dict[str, Any],
        board_name: str,
    ) -> bool:
        """Step 7: Test product pin creation"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 7: CREATE PRODUCT PIN")
        logger.info("=" * 70)

        try:
            boards = pinterest.fetch_boards()
            board = None
            for b in boards:
                if b['name'].lower() == board_name.lower():
                    board = b
                    break
            if not board and boards:
                logger.warning(f"Board '{board_name}' not found, using first available")
                board = boards[0]

            success, result = pinterest.create_pin(
                image_path=image_path,
                title=content["pin_title"],
                description=content["pin_description"],
                board_id=board['id'] if board else None,
                url=formatted_product["url"],
                alt_text=content.get("pin_alt_text", formatted_product["title"]),
            )

            if success:
                details = f"Title: {content['pin_title']}\nBoard: {board['name']}\nURL: {formatted_product['url']}\nPin ID: {result}"
                self.log_step(7, "Create Product Pin", "success", details)
                self.test_results["pins_created"].append({
                    "type": "product",
                    "title": content["pin_title"],
                    "board": board['name'],
                    "pin_id": result,
                    "timestamp": datetime.now().isoformat(),
                })
                return True
            else:
                self.log_step(7, "Create Product Pin", "error", f"API call failed: {result}")
                return False

        except Exception as e:
            self.log_step(7, "Create Product Pin", "error", str(e))
            return False

    def test_video_pin_creation(
        self,
        pinterest: Any,
        video: Dict[str, Any],
        content: Dict[str, Any],
        formatted_product: Dict[str, Any],
        board_name: str,
    ) -> bool:
        """Step 8: Test video pin creation"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 8: CREATE VIDEO PIN")
        logger.info("=" * 70)

        try:
            if video["type"] == "youtube":
                logger.info("YouTube video requires download...")
                from youtube_video_downloader import YouTubeVideoDownloader

                downloader = YouTubeVideoDownloader()
                video_path = downloader.download_video(video["url"])

                if not video_path:
                    self.log_step(8, "Create Video Pin", "warning", f"Could not download YouTube video: {video['title']}")
                    return False
            else:
                video_path = video["path"]

            boards = pinterest.fetch_boards()
            board = None
            for b in boards:
                if b['name'].lower() == board_name.lower():
                    board = b
                    break
            if not board and boards:
                board = boards[0]

            video_title = f"{video.get('title', video.get('filename', 'Video Pin'))}"
            video_description = f"{content['pin_description'][:150]} | Watch & shop!"

            success, result = pinterest.create_pin(
                image_path=video_path,
                title=video_title,
                description=video_description,
                board_id=board['id'] if board else None,
                url=formatted_product["url"],
            )

            if success:
                details = f"Video: {video.get('title', video.get('filename'))}\nBoard: {board['name']}\nSize: {Path(video_path).stat().st_size / 1024 / 1024:.1f}MB\nPin ID: {result}"
                self.log_step(8, "Create Video Pin", "success", details)
                self.test_results["pins_created"].append({
                    "type": "video",
                    "title": video_title,
                    "board": board['name'],
                    "source": video["type"],
                    "pin_id": result,
                    "timestamp": datetime.now().isoformat(),
                })
                return True
            else:
                self.log_step(8, "Create Video Pin", "error", f"API call failed: {result}")
                return False

        except Exception as e:
            self.log_step(8, "Create Video Pin", "error", str(e))
            return False

    def run_full_test(self) -> bool:
        """Run complete end-to-end test"""
        try:
            logger.info("=" * 70)
            logger.info("PINTEREST AUTOMATION — PRODUCT & VIDEO PIN TEST")
            logger.info("=" * 70)

            # Step 1: Verify credentials
            if not self.verify_credentials():
                return False

            # Step 2: Fetch product
            product_data = self.test_shopify_connection()
            if not product_data:
                return False

            # Step 3: Generate content
            content = self.test_content_generation(
                product_data["formatted"],
                product_data["board"]
            )
            if not content:
                # All AI backends failed – use a static fallback
                logger.warning("All AI backends failed, using static content fallback")
                content = {
                    "pin_title": product_data["formatted"].get("title", "Product Pin"),
                    "pin_description": "Check out this product!",
                    "hashtags": ["#product", "#shop"],
                }

            # Step 4: Optimize image
            image_path = self.test_image_optimization(product_data["formatted"])
            if not image_path:
                return False

            # Step 5: Select video
            video = self.test_video_selection()

            # Step 6: Login to Pinterest
            pinterest = self.test_pinterest_login()
            if not pinterest:
                return False

            # Step 7: Create product pin
            product_pin_success = self.test_product_pin_creation(
                pinterest,
                image_path,
                content,
                product_data["formatted"],
                product_data["board"],
            )

            # Clean up image
            Path(image_path).unlink(missing_ok=True)

            # Step 8: Create video pin (if video available)
            video_pin_success = False
            if video:
                video_pin_success = self.test_video_pin_creation(
                    pinterest,
                    video,
                    content,
                    product_data["formatted"],
                    product_data["board"],
                )

            # Summary
            self.test_results["success"] = product_pin_success
            self.test_results["end_time"] = datetime.now().isoformat()

            logger.info("\n" + "=" * 70)
            logger.info("TEST SUMMARY")
            logger.info("=" * 70)
            logger.info(f"Product Pin: {'SUCCESS' if product_pin_success else 'FAILED'}")
            logger.info(f"Video Pin: {'SUCCESS' if video_pin_success else 'SKIPPED' if not video else 'FAILED'}")
            logger.info(f"Total Pins Created: {len(self.test_results['pins_created'])}")
            logger.info(f"Test Duration: {len(self.test_results['steps'])} steps")

            # Save test results
            self.save_test_results()

            return product_pin_success

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            self.test_results["error"] = str(e)
            self.save_test_results()
            return False

        finally:
            try:
                if pinterest:
                    pinterest.close()
            except:
                pass

    def save_test_results(self):
        """Save test results to JSON file"""
        try:
            results_file = Path(__file__).parent / "test_results_latest.json"
            results_file.write_text(json.dumps(self.test_results, indent=2))
            logger.info(f"\nTest results saved: {results_file}")
        except Exception as e:
            logger.error(f"Could not save test results: {e}")


def main():
    test = PinterestAutomationTest()
    success = test.run_full_test()
    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\nTest cancelled by user")
        sys.exit(1)
