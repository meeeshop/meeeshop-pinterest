"""
pinterest_daily.py — Daily Pinterest automation orchestrator
Safely posts products to boards without triggering Pinterest blocks
Rotates boards, spacing, timestamps to mimic organic behavior
"""

import os
import json
import logging
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
from urllib.parse import urljoin

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest, select_board_for_product
from content_generator import generate_content_package
from video_picker import VideoPicker, EnvLoader

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "posting_history.json"
COOLDOWN_HOURS = 2
MAX_PINS_PER_DAY = 19
BOARD_ROTATION_COOLDOWN = 24  # Don't post same board twice in 24h


def load_history() -> Dict[str, Any]:
    """Load posting history"""
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"posts": [], "board_last_used": {}, "daily_count": 0, "last_post_time": None}


def save_history(history: Dict[str, Any]):
    """Save posting history"""
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def should_post_to_board(board_name: str, history: Dict[str, Any]) -> bool:
    """Check if safe to post to board (avoid algorithm blocks)"""

    last_used = history["board_last_used"].get(board_name)
    if not last_used:
        return True

    last_used_time = datetime.fromisoformat(last_used)
    hours_since = (datetime.now() - last_used_time).total_seconds() / 3600

    if hours_since < BOARD_ROTATION_COOLDOWN:
        logger.warning(f"Board '{board_name}' posted {hours_since:.1f}h ago, skipping")
        return False

    return True


def reset_daily_count():
    """Reset daily post count at midnight"""
    history = load_history()
    last_post = history.get("last_post_time")

    if last_post:
        last_post_date = datetime.fromisoformat(last_post).date()
        today = datetime.now().date()
        if last_post_date != today:
            history["daily_count"] = 0
            save_history(history)

    return history["daily_count"]


def can_post_today(history: Dict[str, Any]) -> bool:
    """Check daily posting limit"""
    if history["daily_count"] >= MAX_PINS_PER_DAY:
        logger.warning(f"Daily limit ({MAX_PINS_PER_DAY}) reached")
        return False
    return True


def should_cooldown(history: Dict[str, Any]) -> bool:
    """Enforce posting cooldown between pins"""
    last_post = history.get("last_post_time")
    if not last_post:
        return False

    last_post_time = datetime.fromisoformat(last_post)
    hours_since = (datetime.now() - last_post_time).total_seconds() / 3600

    if hours_since < COOLDOWN_HOURS:
        wait_mins = int((COOLDOWN_HOURS - hours_since) * 60)
        logger.info(f"Cooldown active: wait {wait_mins} min until next post")
        return True

    return False


def download_image(url: str, save_path: Path) -> bool:
    """Download product image for pinning"""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        logger.info(f"Downloaded image: {save_path.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


def get_video_from_youtube_repo() -> Optional[str]:
    """Get video from meeeshop-youtube outputs (if available)"""
    youtube_repo = Path(__file__).parent.parent / "meeeshop-youtube"
    video_dirs = [
        youtube_repo / "videos",
        youtube_repo / "output",
        youtube_repo / "shorts",
    ]

    for video_dir in video_dirs:
        if video_dir.exists():
            videos = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.webm"))
            if videos:
                video = random.choice(videos)
                logger.info(f"Using video: {video.name}")
                return str(video)

    logger.warning("No videos found in meeeshop-youtube")
    return None


def post_pin(
    client: PinterestClient,
    product_data: Dict[str, Any],
    board_name: str,
    content: Dict[str, Any],
) -> bool:
    """Post pin to Pinterest"""

    # Download image
    image_file = Path("/tmp") / f"pin_{product_data['product_id']}.jpg"
    if not download_image(product_data["image_url"], image_file):
        return False

    # Create pin
    success = client.create_pin(
        image_or_video_path=str(image_file),
        title=content["pin_title"],
        description=content["pin_description"],
        board_name=board_name,
        url=product_data["url"],
        alt_text=product_data["image_alt"],
    )

    if success:
        image_file.unlink(missing_ok=True)
        logger.info(f"✓ Posted to '{board_name}': {content['pin_title']}")
    else:
        logger.error(f"✗ Failed to post: {content['pin_title']}")

    return success


def run_daily_posting(use_video: bool = False):
    """Main daily posting orchestrator

    Args:
        use_video: If True, prioritize videos from meeeshop-youtube repo or YouTube channel
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Load credentials from meeeshop-youtube/.env if available
    EnvLoader.load_youtube_env()

    # Load credentials
    pinterest_email = os.getenv("PINTEREST_EMAIL")
    pinterest_password = os.getenv("PINTEREST_PASSWORD")
    shopify_url = os.getenv("SHOPIFY_STORE_URL")
    shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    store_base_url = os.getenv("STORE_BASE_URL", "https://us.meeeshop.com")

    if not all([pinterest_email, pinterest_password, shopify_url, shopify_token]):
        raise ValueError("Missing required credentials in .env")

    # Load history & check limits
    history = load_history()
    reset_daily_count()

    if should_cooldown(history):
        logger.info("Skipping: in cooldown period")
        return

    if not can_post_today(history):
        logger.info("Skipping: daily limit reached")
        return
        return

    # Initialize clients
    pinterest = PinterestClient()
    shopify = ShopifyClient(shopify_url, shopify_token)

    try:
        # Login to Pinterest
        if not pinterest.login():
            logger.error("Pinterest login failed")
            return

        # Fetch boards
        boards = pinterest.fetch_boards()
        if not boards:
            logger.error("No boards found")
            return

        # Fetch products
        products = shopify.get_products(limit=20)
        if not products:
            logger.error("No products found")
            return

        # Filter out recently posted products
        posted_ids = {post["product_id"] for post in history.get("posts", [])}
        available_products = [p for p in products if p["id"] not in posted_ids]

        if not available_products:
            logger.info("All products already posted this week")
            return

        # Select random product
        product = random.choice(available_products)
        formatted = format_product_for_pinterest(product, store_base_url)
        board = select_board_for_product(formatted)
        # Time‑zone filtering: only post if current UTC hour matches board schedule
        try:
            tz_map = json.load((Path(__file__).parent / "us_timezones.json").open("r", encoding="utf-8"))
            board_hour = int(tz_map.get(board, "0"))
            if board_hour != datetime.utcnow().hour:
                logger.info(f"Skipping board '{board}' due to time zone schedule (UTC{board_hour})")
                return
        except Exception as e:
            logger.warning(f"Failed to load time‑zone mapping: {e}")

        # Verify board exists & rotation safe
        if board not in boards:
            logger.warning(f"Board '{board}' not found, using random")
            board = random.choice(list(boards.keys()))

        if not should_post_to_board(board, history):
            logger.info(f"Skipping board '{board}' (rotation cooldown)")
            return

        # Generate content
        logger.info(f"Generating content for: {formatted['title']}")
        content = generate_content_package(formatted, board)

        # Try to add video if enabled
        video_file = None
        if use_video:
            logger.info("Looking for video to include...")
            video_picker = VideoPicker(use_youtube=True)
            video = video_picker.pick_video()
            if video:
                if video["type"] == "local":
                    video_file = video["path"]
                    logger.info(f"✓ Using local video: {video['filename']}")
                else:
                    # YouTube video - would need download logic
                    logger.info(f"Found YouTube video: {video['title']} (would need download)")

        # Post pin (with video if available)
        media_path = video_file or formatted["image_url"]
        if post_pin(pinterest, formatted, board, content):
            history["posts"].append({
                "product_id": product["id"],
                "title": formatted["title"],
                "board": board,
                "timestamp": datetime.now().isoformat(),
            })
            history["board_last_used"][board] = datetime.now().isoformat()
            history["daily_count"] += 1
            history["last_post_time"] = datetime.now().isoformat()
            save_history(history)

            logger.info(f"✓ Daily posting complete. Count: {history['daily_count']}/{MAX_PINS_PER_DAY}")
        else:
            logger.error("Pin posting failed")

    except Exception as e:
        logger.error(f"Posting error: {e}", exc_info=True)


if __name__ == "__main__":
    run_daily_posting()
