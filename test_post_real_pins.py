#!/usr/bin/env python3
"""
test_post_real_pins.py - Actually posts real pins to Pinterest

Posts:
  1. Product pin: Shopify product image + URL (fetched live)
  2. Video pin: YouTube video thumbnail (from past 2-3 days)

Check results at: https://www.pinterest.com/meeeshop/_created/
"""

import os
import sys
import json
import logging
import requests
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load env files
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

youtube_env = Path(__file__).parent.parent / "meeeshop-youtube" / ".env"
if youtube_env.exists():
    load_dotenv(youtube_env)

# Windows UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("test_post_real_pins.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def fetch_shopify_product():
    """Fetch one active Shopify product with image"""
    store_url = os.getenv("SHOPIFY_STORE_URL", "").rstrip("/")
    token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    base_url = os.getenv("STORE_BASE_URL", "").rstrip("/")

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    url = f"{store_url}/admin/api/2024-01/products.json"
    params = {
        "limit": 5,
        "status": "active",
        "published_status": "published",
        "fields": "id,title,handle,images,product_type,tags,variants",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    for p in resp.json().get("products", []):
        if p.get("images"):
            img = p["images"][0]
            variants = p.get("variants", [])
            return {
                "product_id": str(p["id"]),
                "title": p["title"],
                "type": p.get("product_type", ""),
                "tags": p.get("tags", "").split(",")[:3],
                "price": variants[0].get("price") if variants else "N/A",
                "image_url": img["src"],
                "image_alt": img.get("alt") or p["title"],
                "url": f"{base_url}/products/{p['handle']}",
            }
    return None


def fetch_youtube_video():
    """Fetch most recent YouTube video from past 3 days"""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    import googleapiclient.discovery

    creds = Credentials.from_authorized_user_info({
        "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
        "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN"),
        "type": "authorized_user",
    })
    if creds.expired:
        creds.refresh(Request())

    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
    since = (datetime.now() - timedelta(days=3)).isoformat() + "Z"

    resp = youtube.search().list(
        part="snippet",
        channelId=os.getenv("YOUTUBE_CHANNEL_ID"),
        type="video",
        order="date",
        maxResults=5,
        publishedAfter=since,
    ).execute()

    videos = resp.get("items", [])
    if not videos:
        return None

    v = videos[0]
    vid_id = v["id"]["videoId"]
    snippet = v["snippet"]
    return {
        "id": vid_id,
        "title": snippet["title"],
        "thumbnail": snippet["thumbnails"]["high"]["url"],
        "url": f"https://www.youtube.com/watch?v={vid_id}",
        "description": snippet.get("description", "")[:200],
    }


def download_image(url: str) -> str:
    """Download image to temp file, return path"""
    suffix = ".jpg" if "jpg" in url.lower() or "jpeg" in url.lower() else ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    tmp.write(resp.content)
    tmp.close()
    logger.info(f"Downloaded image ({len(resp.content)//1024}KB): {tmp.name}")
    return tmp.name


def get_board_id_by_name(client, board_name: str):
    """Look up real board ID from Pinterest API"""
    boards = client.client.boards()
    for board in boards:
        name = board.get("name", "")
        if name.lower() == board_name.lower():
            return board.get("id")
    # Fallback: partial match
    for board in boards:
        name = board.get("name", "")
        if board_name.lower() in name.lower():
            bid = board.get("id")
            logger.info(f"Partial match: '{name}' -> {bid}")
            return bid
    return None


def post_product_pin(client, product):
    """Post product pin to Pinterest"""
    from board_mapping import get_board_for_product
    from content_generator import generate_pinterest_title, generate_pinterest_description

    logger.info("=" * 60)
    logger.info("POSTING PRODUCT PIN")
    logger.info("=" * 60)
    logger.info(f"Product: {product['title']}")
    logger.info(f"Price: ${product['price']}")
    logger.info(f"URL: {product['url']}")

    board_name = get_board_for_product(product["title"], product["type"])
    title = generate_pinterest_title(product)
    description = generate_pinterest_description(product, "Women's Fashion")

    logger.info(f"Board: {board_name}")
    logger.info(f"Title: {title}")
    logger.info(f"Description: {description[:80]}...")

    board_id = get_board_id_by_name(client, board_name)
    if not board_id:
        logger.error(f"Board '{board_name}' not found on Pinterest account")
        return False

    logger.info(f"Board ID: {board_id}")

    image_path = download_image(product["image_url"])
    try:
        success, result = client.create_pin(
            image_path=image_path,
            title=title,
            description=description,
            board_id=board_id,
            url=product["url"],
            alt_text=product["image_alt"],
        )
    finally:
        Path(image_path).unlink(missing_ok=True)

    if success:
        logger.info(f"[OK] Product pin created! Pin ID: {result}")
        logger.info(f"View at: https://www.pinterest.com/meeeshop/_created/")
    else:
        logger.error(f"[FAILED] Product pin: {result}")

    return success


def post_video_pin(client, video):
    """Post YouTube video pin using thumbnail image"""
    logger.info("=" * 60)
    logger.info("POSTING VIDEO PIN")
    logger.info("=" * 60)
    logger.info(f"Video: {video['title']}")
    logger.info(f"URL: {video['url']}")

    # Use high-traffic board for YouTube videos
    board_name = "New Trendy Women Apparel"
    board_id = get_board_id_by_name(client, board_name)
    if not board_id:
        logger.error(f"Board '{board_name}' not found")
        return False

    title = video["title"][:100]
    description = f"Watch on YouTube: {video['url']}\n\nShop our latest styles at us.meeeshop.com"

    logger.info(f"Board: {board_name} (ID: {board_id})")

    image_path = download_image(video["thumbnail"])
    try:
        success, result = client.create_pin(
            image_path=image_path,
            title=title,
            description=description,
            board_id=board_id,
            url=video["url"],
        )
    finally:
        Path(image_path).unlink(missing_ok=True)

    if success:
        logger.info(f"[OK] Video pin created! Pin ID: {result}")
        logger.info(f"View at: https://www.pinterest.com/meeeshop/_created/")
    else:
        logger.error(f"[FAILED] Video pin: {result}")

    return success


def main():
    logger.info("=" * 60)
    logger.info("REAL PINTEREST PIN POSTING TEST")
    logger.info(f"Started: {datetime.now()}")
    logger.info("=" * 60)

    results = {"product_pin": False, "video_pin": False, "errors": []}

    # Step 1: Login to Pinterest
    logger.info("\nStep 1: Logging into Pinterest...")
    from pinterest_client import PinterestClient
    client = PinterestClient()
    if not client.login():
        logger.error("Pinterest login FAILED - check credentials")
        return

    logger.info("Pinterest login OK")

    # Step 2: Fetch Shopify product
    logger.info("\nStep 2: Fetching Shopify product...")
    try:
        product = fetch_shopify_product()
        if product:
            logger.info(f"Got product: {product['title']}")
        else:
            logger.error("No Shopify products found")
            results["errors"].append("No Shopify products found")
    except Exception as e:
        logger.error(f"Shopify fetch failed: {e}")
        results["errors"].append(f"Shopify: {e}")
        product = None

    # Step 3: Fetch YouTube video
    logger.info("\nStep 3: Fetching YouTube video...")
    try:
        video = fetch_youtube_video()
        if video:
            logger.info(f"Got video: {video['title']}")
        else:
            logger.warning("No YouTube videos found in past 3 days")
    except Exception as e:
        logger.error(f"YouTube fetch failed: {e}")
        results["errors"].append(f"YouTube: {e}")
        video = None

    # Step 4: Post product pin
    if product:
        logger.info("\nStep 4: Posting product pin...")
        try:
            results["product_pin"] = post_product_pin(client, product)
        except Exception as e:
            logger.error(f"Product pin failed: {e}")
            results["errors"].append(f"Product pin: {e}")
    else:
        logger.warning("Skipping product pin (no product data)")

    # Step 5: Post video pin
    if video:
        logger.info("\nStep 5: Posting video pin...")
        try:
            results["video_pin"] = post_video_pin(client, video)
        except Exception as e:
            logger.error(f"Video pin failed: {e}")
            results["errors"].append(f"Video pin: {e}")
    else:
        logger.warning("Skipping video pin (no video found)")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Product pin: {'POSTED' if results['product_pin'] else 'FAILED'}")
    logger.info(f"Video pin:   {'POSTED' if results['video_pin'] else 'FAILED/SKIPPED'}")

    if results["errors"]:
        logger.info("\nErrors:")
        for e in results["errors"]:
            logger.info(f"  - {e}")

    if results["product_pin"] or results["video_pin"]:
        logger.info("\nCheck your pins at:")
        logger.info("  https://www.pinterest.com/meeeshop/_created/")

    # Save results
    out = Path(__file__).parent / "test_post_real_pins_results.json"
    out.write_text(json.dumps({**results, "timestamp": datetime.now().isoformat()}, indent=2, default=str), encoding="utf-8")
    logger.info(f"\nResults saved: {out.name}")


if __name__ == "__main__":
    main()
