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

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest
from content_generator import generate_content_package
from video_picker import EnvLoader
from image_overlay import add_text_overlay

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "posting_history.json"
MAX_PINS_PER_DAY = 17     # all posted in one daily run

# Ordered board rotation: covers every major audience segment across the day's batch.
# First boards are highest-traffic; order ensures variety across the 17-pin sequence.
DAILY_BOARD_ROTATION = [
    "Trends",                    # 1 — highest traffic
    "Dresses",                   # 2 — top category
    "Best selling products",     # 3 — social proof
    "Outfit Ideas",              # 4 — discovery
    "Shirts & Tops",             # 5 — category
    "Style Ideas",               # 6 — lifestyle
    "Jeans",                     # 7 — category
    "Everyday Style",            # 8 — lifestyle
    "Sweaters",                  # 9 — category
    "Simple Outfits",            # 10 — discovery
    "Coats & Jackets",           # 11 — category
    "Chic & Effortless Styles",  # 12 — lifestyle
    "Pants & Leggings",          # 13 — category
    "Ootd #ootd",                # 14 — hashtag discovery
    "New",                       # 15 — recency traffic
    "Wardrobe Must Haves",       # 16 — lifestyle
    "Woman Fashion!",            # 17 — broad audience
]


def load_history() -> Dict[str, Any]:
    """Load posting history"""
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"posts": [], "board_last_used": {}, "daily_count": 0, "last_post_time": None}


def save_history(history: Dict[str, Any]):
    """Save posting history"""
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")



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
    board_id: str,
    content: Dict[str, Any],
) -> bool:
    """Post pin to Pinterest with image overlay"""

    # Download image
    image_file = Path("/tmp") / f"pin_{product_data['product_id']}.jpg"
    if not download_image(product_data["image_url"], image_file):
        logger.error(f"Failed to download image for pin: {content['pin_title']}")
        return False

    try:
        # Add text overlay (title + CTA) to image
        overlay_file = Path("/tmp") / f"pin_overlay_{product_data['product_id']}.jpg"
        overlay_image = add_text_overlay(
            str(image_file),
            title=content["pin_title"],
            cta="Shop Now",
            price=product_data.get("price"),
            output_path=str(overlay_file),
        )

        if not overlay_image:
            logger.warning("Image overlay failed, posting without overlay")
            overlay_image = str(image_file)

        logger.info(f"Creating pin: {content['pin_title']}")

        # Add delay to allow Pinterest to process upload before creating pin
        time.sleep(2)

        success, pin_id = client.create_pin(
            image_path=overlay_image,
            title=content["pin_title"],
            description=content["pin_description"],
            board_id=board_id,
            url=product_data["url"],
            alt_text=product_data["image_alt"],
        )

        if success:
            image_file.unlink(missing_ok=True)
            Path(overlay_image).unlink(missing_ok=True)
            logger.info(f"✓ Posted successfully: {content['pin_title']} (ID: {pin_id})")
            return True
        else:
            logger.error(f"✗ Failed to post: {content['pin_title']} - {pin_id}")
            return False

    except Exception as e:
        logger.error(f"Exception creating pin: {e}", exc_info=True)
        image_file.unlink(missing_ok=True)
        return False


def pick_board(
    index: int,
    boards: List[Dict],
    used_boards: set,
    formatted: Dict[str, Any],
) -> Optional[Dict]:
    """Pick board: category-specific boards first, then rotation for generic products."""
    from board_mapping import CATEGORY_TO_BOARDS

    boards_by_name = {b["name"].lower(): b for b in boards}

    def find(name: str) -> Optional[Dict]:
        b = boards_by_name.get(name.lower())
        if b:
            return b
        for board in boards:
            if name.lower() in board["name"].lower():
                return board
        return None

    def category_key(text: str) -> str:
        for key in ["dress", "top", "blouse", "tank", "shirt", "jeans", "jacket",
                    "coat", "pants", "legging", "skirt", "sweater", "cardigan",
                    "bag", "backpack", "shoe", "boot", "flat", "jumpsuit", "romper"]:
            if key in text:
                if key in ("blouse", "tank", "shirt"): return "top"
                if key in ("coat",): return "jacket"
                if key in ("legging",): return "pants"
                if key in ("boot", "flat"): return "shoe"
                if key in ("backpack",): return "bag"
                if key in ("romper",): return "jumpsuit"
                return key
        return "default"

    search = f"{formatted.get('title','').lower()} {formatted.get('product_type','').lower()}"
    cat = category_key(search)

    # For non-generic products, try category-specific boards first
    if cat != "default":
        for board_name in CATEGORY_TO_BOARDS.get(cat, []):
            b = find(board_name)
            if b and b["name"] not in used_boards:
                return b

    # Walk the rotation list starting at index, skip already-used boards
    rotation = DAILY_BOARD_ROTATION
    for i in range(len(rotation)):
        candidate = rotation[(index + i) % len(rotation)]
        b = find(candidate)
        if b and b["name"] not in used_boards:
            return b

    # Anything unused
    available = [b for b in boards if b["name"] not in used_boards]
    return random.choice(available) if available else random.choice(boards)


def run_daily_posting(use_video: bool = False):
    """Post all MAX_PINS_PER_DAY pins in a single run with short delays between each.

    One workflow trigger per day — logs in once, posts all pins, done in ~20 min.
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    EnvLoader.load_youtube_env()

    pinterest_email = os.getenv("PINTEREST_EMAIL")
    pinterest_password = os.getenv("PINTEREST_PASSWORD")
    shopify_url = os.getenv("SHOPIFY_STORE_URL")
    shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    store_base_url = os.getenv("STORE_BASE_URL", "https://us.meeeshop.com")

    if not all([pinterest_email, pinterest_password, shopify_url, shopify_token]):
        raise ValueError("Missing required credentials in .env")

    target = int(os.getenv("PINS_TO_POST", str(MAX_PINS_PER_DAY)))
    logger.info(f"Daily run starting — target: {target} pins")

    history = load_history()
    reset_daily_count()

    already_today = history["daily_count"]
    if already_today >= MAX_PINS_PER_DAY:
        logger.info(f"Daily cap already reached ({already_today}), skipping")
        return

    target = min(target, MAX_PINS_PER_DAY - already_today)

    pinterest = PinterestClient()
    shopify = ShopifyClient(shopify_url, shopify_token)

    try:
        if not pinterest.login():
            raise RuntimeError("Pinterest login failed")

        boards = pinterest.fetch_boards()
        if not boards:
            raise RuntimeError("No boards found — check Pinterest authentication")
        logger.info(f"Fetched {len(boards)} boards")

        products = shopify.get_products(limit=50)
        if not products:
            raise RuntimeError("No products found — check Shopify credentials")
        logger.info(f"Fetched {len(products)} products")

        # Exclude products posted in the last 7 days
        week_ago = datetime.now() - timedelta(days=7)
        recent_ids = {
            p["product_id"]
            for p in history.get("posts", [])
            if datetime.fromisoformat(p["timestamp"]) > week_ago
        }
        pool = [p for p in products if p["id"] not in recent_ids] or products
        random.shuffle(pool)

        posted = 0
        used_boards: set = set()
        product_index = 0

        while posted < target and product_index < len(pool):
            product = pool[product_index]
            product_index += 1

            formatted = format_product_for_pinterest(product, store_base_url)
            board_info = pick_board(posted, boards, used_boards, formatted)
            if not board_info:
                logger.warning("No board available, skipping product")
                continue

            board = board_info["name"]
            board_id = board_info["id"]
            logger.info(f"Pin {posted + 1}/{target} → {board}")

            content = generate_content_package(formatted, board)

            if not post_pin(pinterest, formatted, board_id, content):
                logger.warning(f"Post failed for '{formatted['title']}', trying next")
                continue

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

            used_boards.add(board)
            posted += 1

            if posted < target:
                delay = random.randint(30, 60)
                logger.info(f"Waiting {delay}s...")
                time.sleep(delay)

        logger.info(f"✓ Done: {posted}/{target} pins posted today")

    except Exception as e:
        logger.error(f"Daily posting error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_daily_posting()
