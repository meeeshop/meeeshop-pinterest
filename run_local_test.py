#!/usr/bin/env python3
"""
run_local_test.py — Test Pinterest posting workflow locally
Tests: Product fetch → Content generation → Video picking → Rich pin ready to post
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

def main():
    logger.info("=" * 70)
    logger.info("📊 PINTEREST POSTING WORKFLOW TEST")
    logger.info("=" * 70)

    # Step 1: Fetch Shopify products
    logger.info("\n✓ Step 1: Fetching Shopify products...")
    try:
        from shopify_products import ShopifyClient, format_product_for_pinterest, select_board_for_product

        shopify_url = os.getenv("SHOPIFY_STORE_URL")
        shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

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

    # Step 2: Format product
    logger.info("\n✓ Step 2: Formatting product for Pinterest...")
    try:
        store_base_url = os.getenv("STORE_BASE_URL", "https://us.meeeshop.com")
        formatted = format_product_for_pinterest(product, store_base_url)
        board = select_board_for_product(formatted)

        logger.info(f"  ✓ Board: {board}")
        logger.info(f"  ✓ Image: {formatted['image_url'][:60]}...")
        logger.info(f"  ✓ URL: {formatted['url']}")

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False

    # Step 3: Generate AI content
    logger.info("\n✓ Step 3: Generating AI content...")
    try:
        from content_generator import generate_content_package

        content = generate_content_package(formatted, board)

        logger.info(f"  ✓ Title: {content['pin_title']}")
        logger.info(f"  ✓ Description: {content['pin_description'][:80]}...")
        logger.info(f"  ✓ Hashtags: {', '.join(content['hashtags'][:5])}...")

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False

    # Step 4: Pick video from YouTube
    logger.info("\n✓ Step 4: Picking video from YouTube channel...")
    try:
        from video_picker import VideoPicker

        picker = VideoPicker(use_youtube=True)
        video = picker.pick_video()

        if video:
            video_title = video.get("title", video.get("filename"))
            video_source = video.get("type", "unknown")
            logger.info(f"  ✓ Video found: {video_title}")
            logger.info(f"  ✓ Source: {video_source}")

            if video_source == "youtube":
                logger.info(f"  ✓ URL: {video.get('url')}")
                logger.info(f"  ✓ Thumbnail: {video.get('thumbnail')[:60]}...")
        else:
            logger.info("  ℹ No video found - will use image as fallback")
            video = None

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        logger.info("  ℹ Continuing with image fallback...")
        video = None

    # Step 5: Prepare rich pin data
    logger.info("\n✓ Step 5: Preparing rich pin data...")
    try:
        rich_pin_data = {
            "product_title": formatted["title"],
            "pin_title": content["pin_title"],
            "pin_description": content["pin_description"],
            "hashtags": content["hashtags"],
            "board": board,
            "media_type": "video" if video else "image",
            "media_url": video.get("url") if video else formatted["image_url"],
            "product_url": formatted["url"],
            "image_alt": formatted.get("image_alt", formatted["title"]),
        }

        logger.info(f"  ✓ Rich pin ready")

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return False

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("✅ WORKFLOW TEST COMPLETE - READY TO POST")
    logger.info("=" * 70)

    logger.info("\n📌 Rich Pin Ready:")
    logger.info(f"\n  Product: {rich_pin_data['product_title']}")
    logger.info(f"  Board: {rich_pin_data['board']}")
    logger.info(f"  Pin Title: {rich_pin_data['pin_title']}")
    logger.info(f"  Description: {rich_pin_data['pin_description'][:100]}...")
    logger.info(f"  Media Type: {rich_pin_data['media_type'].upper()}")
    if video:
        logger.info(f"  Video: {video.get('title', video.get('filename'))}")
    logger.info(f"  Product URL: {rich_pin_data['product_url']}")

    logger.info("\n🚀 Next Steps:")
    logger.info("  1. Pinterest cookies need to be saved")
    logger.info("  2. Run: python pinterest_daily.py (posts to Pinterest)")
    logger.info("  3. Check Pinterest to verify rich pin was posted")

    return True

if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⏹ Test cancelled by user")
        exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        exit(1)
