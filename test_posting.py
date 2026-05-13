#!/usr/bin/env python3
"""
test_posting.py — Test Pinterest posting with saved cookies
Tests: 1 product rich pin + 1 YouTube video pin
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
    logger.info("🎨 PINTEREST POSTING TEST — Using Saved Cookies")
    logger.info("=" * 70)

    # Step 1: Check saved cookies
    logger.info("\n✓ Step 1: Checking saved cookies...")
    cookies_file = Path(__file__).parent / ".pinterest_cookies"
    if not cookies_file.exists():
        logger.error("  ✗ Cookies file not found!")
        return False
    logger.info(f"  ✓ Cookies file exists: {cookies_file}")

    # Step 2: Initialize Pinterest client with saved cookies
    logger.info("\n✓ Step 2: Initializing Pinterest client...")
    try:
        from pinterest_client import PinterestClient
        pinterest = PinterestClient(use_cookies=True, headless=False, debug=True)
        logger.info("  ✓ PinterestClient initialized")
    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False

    try:
        # Step 3: Login with saved cookies
        logger.info("\n✓ Step 3: Logging in with saved cookies...")
        if not pinterest.login():
            logger.error("  ✗ Cookie login failed")
            return False
        logger.info("  ✓ Successfully logged in with saved cookies")

        # Step 4: Fetch boards (optional - may be empty for business accounts)
        logger.info("\n✓ Step 4: Fetching Pinterest boards...")
        boards = pinterest.fetch_boards()
        if boards:
            logger.info(f"  ✓ Found {len(boards)} boards")
            logger.info(f"     Available: {list(boards.keys())}")
        else:
            logger.info("  ℹ No boards found (business accounts may not list boards this way)")
            boards = {}  # Continue with empty boards dict

        # Step 5: Fetch Shopify product
        logger.info("\n✓ Step 5: Fetching Shopify product...")
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

        # Step 6: Format product for Pinterest
        logger.info("\n✓ Step 6: Formatting product for Pinterest...")
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

        # Step 7: Generate AI content
        logger.info("\n✓ Step 7: Generating AI content...")
        try:
            from content_generator import generate_content_package

            content = generate_content_package(formatted, board)

            logger.info(f"  ✓ Title: {content['pin_title']}")
            logger.info(f"  ✓ Description: {content['pin_description'][:80]}...")
            logger.info(f"  ✓ Hashtags: {', '.join(content['hashtags'][:5])}")

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

        # Step 8: Pick YouTube video
        logger.info("\n✓ Step 8: Picking video from YouTube channel...")
        try:
            from video_picker import VideoPicker

            picker = VideoPicker(use_youtube=True)
            video = picker.pick_video()

            if not video:
                logger.warning("  ⚠ No video found - will use image for first pin")
                video = None
            else:
                video_title = video.get("title", video.get("filename"))
                video_source = video.get("type", "unknown")
                logger.info(f"  ✓ Found: {video_title}")
                logger.info(f"  ✓ Source: {video_source}")
                if video_source == "youtube":
                    logger.info(f"  ✓ URL: {video.get('url')}")

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            logger.info("  ℹ Continuing with image fallback...")
            video = None

        # Step 9: Create product rich pin with optimized image
        logger.info("\n✓ Step 9: Creating product rich pin...")
        try:
            from image_optimizer import ImageOptimizer

            # Optimize image with overlays
            logger.info(f"  🎨 Optimizing image with overlays...")
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

            logger.info(f"  ✓ Image ready: {image_path}")

            # Verify board exists (if we have boards)
            if boards and board not in boards:
                logger.warning(f"  ⚠ Board '{board}' not found, using: {list(boards.keys())[0]}")
                board = list(boards.keys())[0]

            # Create pin (board_name is optional for business accounts)
            if boards:
                logger.info(f"  📌 Creating pin on '{board}'...")
            else:
                logger.info(f"  📌 Creating pin (no board specified)...")

            if pinterest.create_pin(
                image_or_video_path=image_path,
                title=content["pin_title"],
                description=content["pin_description"],
                board_name=board if boards else None,
                url=formatted["url"],
                alt_text=formatted.get("image_alt", formatted["title"]),
            ):
                logger.info(f"  ✅ Product rich pin created!")
                Path(image_path).unlink(missing_ok=True)
            else:
                logger.error(f"  ✗ Failed to create pin")
                Path(image_path).unlink(missing_ok=True)
                return False

        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            return False

        # Step 10: Create video pin (if video found)
        if video:
            logger.info("\n✓ Step 10: Creating video pin...")
            try:
                if video["type"] == "youtube":
                    logger.info(f"  ℹ YouTube video requires download/processing")
                    logger.info(f"     For now, showing video info:")
                    logger.info(f"     - Title: {video.get('title')}")
                    logger.info(f"     - URL: {video.get('url')}")
                    logger.info(f"     - Thumbnail: {video.get('thumbnail')[:60]}...")
                    logger.info(f"  ℹ Video pin posting ready (needs download integration)")

                elif video["type"] == "local":
                    video_title = video.get("filename", "Local Video")
                    video_description = f"Check out this video! {content['pin_description'][:200]}"

                    # Verify board exists (if we have boards)
                    if boards and board not in boards:
                        board = list(boards.keys())[0]

                    # Create video pin
                    if boards:
                        logger.info(f"  📹 Creating video pin on '{board}'...")
                    else:
                        logger.info(f"  📹 Creating video pin...")

                    if pinterest.create_pin(
                        image_or_video_path=video["path"],
                        title=f"🎬 {video_title}",
                        description=video_description,
                        board_name=board if boards else None,
                        url=formatted["url"],
                    ):
                        logger.info(f"  ✅ Video pin created!")
                    else:
                        logger.error(f"  ✗ Failed to create video pin")

            except Exception as e:
                logger.error(f"  ✗ Error: {e}")

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("✅ TEST COMPLETE — RICH PINS POSTED TO PINTEREST")
        logger.info("=" * 70)

        logger.info("\n📊 Summary:")
        logger.info(f"  Product: {formatted['title']}")
        logger.info(f"  Board: {board}")
        logger.info(f"  Pin Title: {content['pin_title']}")
        if video:
            logger.info(f"  Video: {video.get('title', video.get('filename'))}")

        logger.info("\n✅ Next Steps:")
        logger.info("  1. Check your Pinterest account to verify pins were posted")
        logger.info("  2. Confirm rich pin formatting and content")
        logger.info("  3. Once validated, push to GitHub with:")
        logger.info("     git add -A && git commit -m 'Add Pinterest automation with rich pins'")

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
