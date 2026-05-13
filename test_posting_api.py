#!/usr/bin/env python3
"""
test_posting_api.py — Test Pinterest posting with py3-pinterest (no Selenium)
Tests: 1 product pin + 1 optional video pin (if available)
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env files
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Load YouTube env for API keys
youtube_env = Path(__file__).parent.parent / "meeeshop-youtube" / ".env"
if youtube_env.exists():
    load_dotenv(youtube_env)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 70)
    logger.info("🎨 PINTEREST POSTING TEST — Using py3-pinterest API")
    logger.info("=" * 70)

    # Step 1: Initialize Pinterest client
    logger.info("\n✓ Step 1: Initializing Pinterest client...")
    try:
        from pinterest_api_client import PinterestAPIClient

        pinterest = PinterestAPIClient()
        if not pinterest.client:
            logger.error("  ✗ Failed to initialize client")
            return False
        logger.info("  ✓ Client initialized")
    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False

    try:
        # Step 2: Login
        logger.info("\n✓ Step 2: Logging in to Pinterest...")
        if not pinterest.login():
            logger.error("  ✗ Login failed")
            return False
        logger.info("  ✓ Successfully logged in")

        # Step 3: Fetch boards
        logger.info("\n✓ Step 3: Fetching Pinterest boards...")
        boards = pinterest.fetch_boards()
        if boards:
            logger.info(f"  ✓ Found {len(boards)} boards")
            logger.info(f"     Available: {list(boards.keys())}")
        else:
            logger.info("  ℹ No boards found (will use default board)")
            boards = {}

        # Step 4: Fetch Shopify product
        logger.info("\n✓ Step 4: Fetching Shopify product...")
        try:
            from shopify_products import ShopifyClient, format_product_for_pinterest, select_board_for_product

            shopify_url = os.getenv("SHOPIFY_STORE_URL")
            shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

            if not shopify_url or not shopify_token:
                logger.error("  ✗ Missing Shopify credentials")
                return False

            shopify = ShopifyClient(shopify_url, shopify_token)
            products = shopify.get_products(limit=1)

            if not products:
                logger.error("  ✗ No products found")
                return False

            product = products[0]
            logger.info(f"  ✓ Found product: {product['title']}")

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

        # Step 5: Format product for Pinterest
        logger.info("\n✓ Step 5: Formatting product for Pinterest...")
        try:
            store_base_url = os.getenv("STORE_BASE_URL", "https://us.meeeshop.com")
            formatted = format_product_for_pinterest(product, store_base_url)
            board = select_board_for_product(formatted)

            logger.info(f"  ✓ Title: {formatted['title']}")
            logger.info(f"  ✓ Board: {board}")
            logger.info(f"  ✓ Image: {formatted['image_url'][:60]}...")
            logger.info(f"  ✓ URL: {formatted['url']}")

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

        # Step 6: Generate AI content
        logger.info("\n✓ Step 6: Generating AI content...")
        try:
            from content_generator import generate_content_package

            content = generate_content_package(formatted, board)

            logger.info(f"  ✓ Title: {content['pin_title']}")
            logger.info(f"  ✓ Description: {content['pin_description'][:80]}...")
            logger.info(f"  ✓ Hashtags: {', '.join(content['hashtags'][:5])}")

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

        # Step 7: Optimize image for Pinterest
        logger.info("\n✓ Step 7: Optimizing image for Pinterest...")
        try:
            from image_optimizer import ImageOptimizer

            optimizer = ImageOptimizer()
            image_path = optimizer.optimize_for_pinterest(
                formatted["image_url"],
                formatted,
                accent_color="rose"
            )

            if not image_path:
                logger.warning("  ⚠ Image optimization failed, using raw image...")
                import requests
                import tempfile

                image_url = formatted["image_url"]
                resp = requests.get(image_url, timeout=10)
                resp.raise_for_status()

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    f.write(resp.content)
                    image_path = f.name

            logger.info(f"  ✓ Image ready: {Path(image_path).name}")

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

        # Step 8: Create product pin
        logger.info("\n✓ Step 8: Creating product pin...")
        try:
            # Verify board exists
            if boards and board not in boards:
                logger.warning(f"  ⚠ Board '{board}' not found, using first available board")
                board = list(boards.keys())[0] if boards else None

            # Create pin
            if boards:
                logger.info(f"  📌 Creating pin on '{board}'...")
            else:
                logger.info(f"  📌 Creating pin...")

            success = pinterest.create_pin(
                image_or_video_path=str(image_path),
                title=content["pin_title"],
                description=content["pin_description"],
                board_name=board,
                url=formatted["url"],
                alt_text=formatted.get("image_alt", formatted["title"]),
            )

            if success:
                logger.info(f"  ✅ Product pin created!")
                Path(image_path).unlink(missing_ok=True)
            else:
                logger.error(f"  ✗ Failed to create pin")
                Path(image_path).unlink(missing_ok=True)
                return False

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

        # Step 9: Try to create video pin if YouTube video available
        logger.info("\n✓ Step 9: Checking for video to post...")
        try:
            from video_picker import VideoPicker

            picker = VideoPicker(use_youtube=True)
            video = picker.pick_video()

            if video and video.get("type") == "youtube":
                logger.info(f"  ✓ Found YouTube video: {video.get('title')}")
                logger.info(f"  ℹ YouTube videos require manual download")
                logger.info(f"     You can post this video manually or integrate youtube_video_downloader.py")

            elif video and video.get("type") == "local":
                logger.info(f"  ✓ Found local video: {video.get('filename')}")

                video_title = video.get("filename", "Local Video")
                video_description = f"Check out this video! {content['pin_description'][:200]}"

                if boards and board not in boards:
                    board = list(boards.keys())[0]

                logger.info(f"  📹 Creating video pin...")
                success = pinterest.create_pin(
                    image_or_video_path=str(video["path"]),
                    title=f"🎬 {video_title}",
                    description=video_description,
                    board_name=board,
                    url=formatted["url"],
                )

                if success:
                    logger.info(f"  ✅ Video pin created!")
                else:
                    logger.warning(f"  ⚠ Video pin creation failed")
            else:
                logger.info(f"  ℹ No video found - skipping video pin")

        except Exception as e:
            logger.warning(f"  ⚠ Video step failed (non-critical): {e}")

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("✅ TEST COMPLETE — PINS POSTED TO PINTEREST")
        logger.info("=" * 70)

        logger.info("\n📊 Summary:")
        logger.info(f"  Product: {formatted['title']}")
        logger.info(f"  Pin Title: {content['pin_title']}")
        logger.info(f"  Description: {content['pin_description']}")

        logger.info("\n✅ Next Steps:")
        logger.info("  1. Check your Pinterest account to verify pins were posted")
        logger.info("  2. Confirm pin formatting and content visibility")
        logger.info("  3. Once validated, push to GitHub for scheduled automation")
        logger.info("     git add -A && git commit -m 'Add Pinterest automation with py3-pinterest'")

        return True

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return False

    finally:
        pinterest.close()


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⏹ Test cancelled by user")
        exit(1)
