"""
pinterest_daily.py — Daily Pinterest automation orchestrator
Safely posts products to boards without triggering Pinterest blocks
Rotates boards, spacing, timestamps to mimic organic behavior
"""

import os
import sys
import json
import logging
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest
from content_generator import generate_content_package
from video_picker import EnvLoader
from image_overlay import add_text_overlay

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "posting_history.json"
MAX_PINS_PER_DAY = 16    # 4 runs × 4 pins across peak USA times
PINS_PER_RUN = 4



def load_history() -> Dict[str, Any]:
    """Load posting history"""
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {
        "posts": [], "board_last_used": {}, "daily_count": 0,
        "last_post_time": None, "board_rotation_cursor": 0,
    }


def advance_board_cursor(history: Dict[str, Any], steps: int, total_boards: int) -> int:
    """Advance and persist the board rotation cursor, returns the starting position."""
    cursor = history.get("board_rotation_cursor", 0) % max(total_boards, 1)
    history["board_rotation_cursor"] = (cursor + steps) % total_boards
    return cursor


def save_history(history: Dict[str, Any]):
    """Save posting history"""
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")



def reset_daily_count():
    """Reset daily post count at midnight — returns updated history"""
    history = load_history()
    last_post = history.get("last_post_time")

    if last_post:
        last_post_date = datetime.fromisoformat(last_post).date()
        today = datetime.now().date()
        if last_post_date != today:
            history["daily_count"] = 0
            save_history(history)

    return history


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
    run_board_pool: List[str],
) -> Optional[Dict]:
    """Pick board: category-specific first, then cycle through this run's board pool.

    run_board_pool is pre-built per run from the full board list via cursor rotation,
    so every board gets reached over time — not just the same 16.
    """
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

    # Try category-specific boards first (non-generic products)
    if cat != "default":
        for board_name in CATEGORY_TO_BOARDS.get(cat, []):
            b = find(board_name)
            if b and b["name"] not in used_boards:
                return b

    # Cycle through this run's board pool (cursor-based, covers all boards over time)
    for i in range(len(run_board_pool)):
        candidate = run_board_pool[(index + i) % len(run_board_pool)]
        b = find(candidate)
        if b and b["name"] not in used_boards:
            return b

    # Last resort: anything unused from full board list
    available = [b for b in boards if b["name"] not in used_boards]
    return random.choice(available) if available else random.choice(boards)


def fetch_all_eligible_products(
    shopify: "ShopifyClient",
    history: Dict[str, Any],
    min_stock: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch ALL active products with stock > min_stock, paginated.

    Excludes products posted in the last 10 days to ensure diversity.
    Returns products in random order ready for posting.
    """
    products = []
    limit = 250
    fields = "id,title,handle,image,images,body_html,vendor,product_type,tags,published_at,variants"
    url = f"{shopify.store_url}/admin/api/2024-01/products.json?status=active&limit={limit}&fields={fields}"

    # Fetch all pages via Link header pagination
    while url:
        try:
            r = requests.get(url, headers=shopify.headers, timeout=15)
            r.raise_for_status()
            batch = r.json().get("products", [])
            products.extend(batch)
            logger.debug(f"Fetched {len(batch)} products, total so far: {len(products)}")

            # Extract next page URL from Link header
            link_header = r.headers.get("Link", "")
            next_url = None
            if link_header:
                for link in link_header.split(","):
                    if 'rel="next"' in link:
                        # Extract URL from <url>; rel="next"
                        next_url = link.split(";")[0].strip().strip("<>")
                        break
            url = next_url
        except Exception as e:
            logger.warning(f"Product fetch error: {e}, continuing with {len(products)} products so far")
            break

    logger.info(f"Fetched {len(products)} total products from Shopify")

    # Filter: active, stock >= min_stock, not posted in last 10 days
    ten_days_ago = datetime.now() - timedelta(days=10)
    recent_ids = {
        p.get("id")
        for p in history.get("posts", [])
        if datetime.fromisoformat(p["timestamp"]) > ten_days_ago
    }

    eligible = [
        p for p in products
        if p.get("id") not in recent_ids
        and any(
            v.get("inventory_quantity", 0) >= min_stock
            for v in p.get("variants", [])
        )
    ]

    logger.info(f"Eligible products (stock>{min_stock}, not in last 10 days): {len(eligible)}")
    random.shuffle(eligible)
    return eligible


def build_run_board_pool(
    all_boards: List[Dict],
    history: Dict[str, Any],
    pins_this_run: int,
) -> List[str]:
    """Build the board pool for this run using cursor rotation across all boards.

    Strategy: 1 priority board + (pins_this_run - 1) boards from cursor window.
    Cursor advances by (pins_this_run - 1) each run, cycling through all boards.
    This ensures every board gets used over a full rotation cycle.
    """
    from board_mapping import MEEESHOP_BOARDS, PRIORITY_BOARDS

    # Build ordered list: live boards sorted by MEEESHOP_BOARDS order, unknowns appended
    live_names = {b["name"] for b in all_boards}
    ordered = [n for n in MEEESHOP_BOARDS if n in live_names]
    extras = [b["name"] for b in all_boards if b["name"] not in set(ordered)]
    all_names = ordered + extras

    if not all_names:
        return [b["name"] for b in all_boards]

    # One priority board for guaranteed reach (rotates through PRIORITY_BOARDS list)
    priority_cursor = history.get("board_rotation_cursor", 0) % len(PRIORITY_BOARDS)
    priority_pick = PRIORITY_BOARDS[priority_cursor % len(PRIORITY_BOARDS)]

    # Fill remaining slots from cursor window
    fill_count = max(pins_this_run - 1, 1)
    cursor = advance_board_cursor(history, fill_count, len(all_names))

    pool = [priority_pick]
    for i in range(fill_count):
        name = all_names[(cursor + i) % len(all_names)]
        if name not in pool:
            pool.append(name)

    logger.info(f"Board pool for this run ({len(pool)} boards, cursor {cursor}/{len(all_names)}): {pool}")
    return pool


def run_daily_posting(use_video: bool = False):
    """Post all MAX_PINS_PER_DAY pins in a single run with short delays between each.

    One workflow trigger per day — logs in once, posts all pins, done in ~20 min.
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    EnvLoader.load_youtube_env()

    pinterest_email = get_secret("PINTEREST_EMAIL")
    pinterest_password = get_secret("PINTEREST_PASSWORD")
    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    if not all([pinterest_email, pinterest_password, shopify_url, shopify_token]):
        raise ValueError("Missing required credentials in .env")

    target = int(os.getenv("PINS_TO_POST", str(PINS_PER_RUN)))
    logger.info(f"Daily run starting — target: {target} pins")

    history = reset_daily_count()

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

        run_board_pool = build_run_board_pool(boards, history, target)
        save_history(history)  # persist cursor advance

        # Fetch ALL products with stock > 20, paginated, exclude last 10 days
        pool = fetch_all_eligible_products(shopify, history, min_stock=20)
        if not pool:
            logger.warning("No eligible products (try lowering stock threshold or checking 10-day window)")
            return

        posted = 0
        used_boards: set = set()
        product_index = 0

        while posted < target and product_index < len(pool):
            product = pool[product_index]
            product_index += 1

            formatted = format_product_for_pinterest(product, store_base_url)
            board_info = pick_board(posted, boards, used_boards, formatted, run_board_pool)
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
