"""
pinterest_refresh.py — Fresh-pin refresh cycle for MeeeShop.

Strategy (Pinterest-safe):
  - Finds products posted 48h+ ago that have refresh slots remaining
  - Creates a BRAND NEW pin image (different template) for the same product URL
  - Posts to a different relevant board than the original
  - Each product gets up to 2 refreshes (48h and 96h after original)
  - New image hash = Pinterest treats it as 100% fresh content, not a repin

Why this is safe:
  - Pinterest only flags SAME image saved to multiple boards (duplicate pin)
  - New image + same URL = fresh pin, full algorithm distribution
  - 48h gap + different board = no spam signals
  - Max 3 total pins per product (original + 2 refreshes) over ~4 days
"""

import os
import sys
import json
import logging
import random
import time
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest
from content_generator import generate_content_package
from video_picker import EnvLoader
from image_overlay import add_text_overlay, PIN_W, PIN_H
from board_mapping import MEEESHOP_BOARDS, CATEGORY_TO_BOARDS

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "posting_history.json"
REFRESH_HISTORY_FILE = Path(__file__).parent / "refresh_history.json"

# Minimum hours after original post before first refresh
FIRST_REFRESH_HOURS = 48
# Minimum hours after first refresh before second refresh
SECOND_REFRESH_HOURS = 48
# Max refreshes per product (keeps total pins per product to 3 across ~4 days)
MAX_REFRESHES_PER_PRODUCT = 2
# Max refresh pins per workflow run
MAX_REFRESHES_PER_RUN = 10


# Board pools per category — used to find a board DIFFERENT from the original.
# Ordered by audience reach (highest traffic first within each category).
REFRESH_BOARD_POOLS = {
    "dress": ["Dressy Outfits", "Cocktail Dresses", "Chic & Effortless Styles",
              "Woman Fashion!", "Festive Styles", "Short Tall dresses", "Outfit Ideas"],
    "top":   ["Camis & Tanks", "Puff Sleeves Tops", "Blouse", "Chic Looks",
              "Cool & Casual Styles", "Effortless Looks", "Ootd #ootd"],
    "jeans": ["Straight Leg Jeans", "Fitted Jeans", "Casual", "Weekend to Workout",
              "Everyday Style", "Ootd #ootd"],
    "jacket": ["Outer wear", "Festive & Flora Fits", "Chic & Cozy Anim...",
               "Edgy Fashion", "Wardrobe Must Haves"],
    "pants": ["Casual", "Weekend to Workout", "Everyday Style",
              "Relaxed Yet Trendy...", "Simple Outfits"],
    "skirt": ["Dressy Outfits", "Festive Styles", "Chic & Effortless Styles",
              "Woman Fashion!", "Outfit Ideas"],
    "sweater": ["Sweaters & Sweater...", "Sweaters for women", "Chic & Cozy Anim...",
                "comfy fall outfits", "Wardrobe Must Haves"],
    "cardigan": ["Sweaters", "Sweaters for women", "Chic & Cozy Anim...",
                 "comfy fall outfits", "Womens shacket"],
    "bag":   ["Handbag #handsips", "Nylon backpack", "Trendy Backpacks",
              "Wardrobe Must Haves", "Best selling products"],
    "shoe":  ["Footwear", "Boat Shoes", "Ankle Strap Flats", "Outfit Ideas"],
    "jumpsuit": ["Rompers_Jumpsuits &...", "Dressy Outfits", "Casual",
                 "Woman Fashion!", "Ootd #ootd"],
    "default": ["Stylish Finds", "Wardrobe Must Haves", "Wardrobe Oozes",
                "Confidence Ladies", "Chic Looks", "Effortless Looks",
                "Cool & Casual Styles", "Simple Outfits"],
}


def load_history() -> Dict[str, Any]:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"posts": [], "board_last_used": {}, "daily_count": 0, "last_post_time": None}


def load_refresh_history() -> Dict[str, Any]:
    if REFRESH_HISTORY_FILE.exists():
        return json.loads(REFRESH_HISTORY_FILE.read_text(encoding="utf-8"))
    return {"refreshes": []}


def save_refresh_history(rh: Dict[str, Any]):
    REFRESH_HISTORY_FILE.write_text(json.dumps(rh, indent=2, default=str), encoding="utf-8")


def save_history(history: Dict[str, Any]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def _category_key(title: str, product_type: str = "") -> str:
    text = f"{title} {product_type}".lower()
    for key in ["dress", "top", "blouse", "tank", "shirt", "jeans", "jacket",
                "coat", "pants", "legging", "skirt", "sweater", "cardigan",
                "bag", "backpack", "shoe", "boot", "flat", "jumpsuit", "romper"]:
        if key in text:
            # Normalize to REFRESH_BOARD_POOLS keys
            if key in ("blouse", "tank", "shirt"):
                return "top"
            if key in ("coat",):
                return "jacket"
            if key in ("legging",):
                return "pants"
            if key in ("boot", "flat"):
                return "shoe"
            if key in ("backpack",):
                return "bag"
            if key in ("romper",):
                return "jumpsuit"
            return key
    return "default"


def pick_refresh_board(
    original_board: str,
    title: str,
    product_type: str,
    boards: List[Dict],
    used_boards_today: set,
) -> Optional[Dict]:
    """Pick a board different from original_board and not used today."""
    boards_by_name = {b["name"].lower(): b for b in boards}

    def find(name: str) -> Optional[Dict]:
        b = boards_by_name.get(name.lower())
        if b:
            return b
        for board in boards:
            if name.lower() in board["name"].lower():
                return board
        return None

    category = _category_key(title, product_type)
    pool = REFRESH_BOARD_POOLS.get(category, REFRESH_BOARD_POOLS["default"])

    for candidate in pool:
        if candidate.lower() == original_board.lower():
            continue
        b = find(candidate)
        if b and b["name"] not in used_boards_today:
            return b

    # Fallback: any board not original and not used today
    for b in boards:
        if b["name"].lower() != original_board.lower() and b["name"] not in used_boards_today:
            return b

    return None



def download_image(url: str, save_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        logger.error(f"Image download failed: {e}")
        return False


def make_refresh_pin_image(
    image_url: str,
    title: str,
    price: Optional[str],
    product_id: str,
    refresh_number: int,
) -> Optional[str]:
    """Download product image and apply a DIFFERENT template than the original pin.

    Original template = MD5(title) % 5 (create_pin_image default).
    Refresh 1 = +2 offset, Refresh 2 = +3 offset — guarantees all three differ.
    """
    tmp_src = Path("/tmp") / f"refresh_src_{product_id}.jpg"
    if not download_image(image_url, tmp_src):
        return None

    original_idx = int(hashlib.md5(title.encode()).hexdigest(), 16) % 5
    new_idx = (original_idx + refresh_number + 1) % 5

    out_path = Path("/tmp") / f"refresh_overlay_{product_id}_r{refresh_number}.jpg"
    result = add_text_overlay(
        str(tmp_src),
        title=title,
        price=price,
        output_path=str(out_path),
        template_index=new_idx,
    )

    tmp_src.unlink(missing_ok=True)
    return result if result else None


def get_candidates(
    history: Dict[str, Any],
    refresh_history: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Find original posts eligible for refresh (48h+ old, refreshes remaining)."""

    now = datetime.now()
    refresh_counts: Dict[str, int] = {}
    last_refresh_time: Dict[str, datetime] = {}

    for r in refresh_history.get("refreshes", []):
        pid = r["product_id"]
        refresh_counts[pid] = refresh_counts.get(pid, 0) + 1
        ts = datetime.fromisoformat(r["timestamp"])
        if pid not in last_refresh_time or ts > last_refresh_time[pid]:
            last_refresh_time[pid] = ts

    candidates = []
    seen_product_ids = set()

    for post in history.get("posts", []):
        pid = post.get("product_id")
        if not pid or pid in seen_product_ids:
            continue
        # Only original posts (no original_id field means it was a first post)
        if post.get("is_refresh"):
            continue
        seen_product_ids.add(pid)

        count = refresh_counts.get(pid, 0)
        if count >= MAX_REFRESHES_PER_PRODUCT:
            continue

        post_time = datetime.fromisoformat(post["timestamp"])
        age_hours = (now - post_time).total_seconds() / 3600

        # First refresh: must be 48h+ since original post
        if count == 0 and age_hours < FIRST_REFRESH_HOURS:
            continue

        # Second refresh: must be 48h+ since last refresh
        if count == 1:
            last = last_refresh_time.get(pid)
            if last and (now - last).total_seconds() / 3600 < SECOND_REFRESH_HOURS:
                continue

        candidates.append({**post, "_refresh_number": count + 1})

    # Prioritise oldest posts first (most overdue for refresh)
    candidates.sort(key=lambda p: p["timestamp"])
    return candidates


def run_refresh_posting():
    """Main entry: create fresh pins for products due for their 48h/96h refresh."""

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

    history = load_history()
    refresh_history = load_refresh_history()

    candidates = get_candidates(history, refresh_history)
    if not candidates:
        logger.info("No products due for refresh today")
        return

    logger.info(f"{len(candidates)} products eligible for refresh")

    pinterest = PinterestClient()
    shopify = ShopifyClient(shopify_url, shopify_token)

    try:
        if not pinterest.login():
            raise RuntimeError("Pinterest login failed")

        boards = pinterest.fetch_boards()
        if not boards:
            raise RuntimeError("No boards found")
        logger.info(f"Fetched {len(boards)} boards")

        # Build full product map from Shopify for image URLs etc.
        products = shopify.get_products(limit=50)
        product_map = {str(p["id"]): p for p in products}

        used_boards_today: set = set()
        refreshed = 0

        for post in candidates:
            if refreshed >= MAX_REFRESHES_PER_RUN:
                break

            pid = str(post["product_id"])
            refresh_num = post["_refresh_number"]
            original_board = post.get("board", "")

            product = product_map.get(pid)
            if not product:
                logger.warning(f"Product {pid} not found in Shopify — skipping")
                continue

            formatted = format_product_for_pinterest(product, store_base_url)

            board_info = pick_refresh_board(
                original_board,
                formatted["title"],
                product.get("product_type", ""),
                boards,
                used_boards_today,
            )
            if not board_info:
                logger.warning(f"No eligible refresh board for '{formatted['title']}'")
                continue

            board = board_info["name"]
            board_id = board_info["id"]
            logger.info(
                f"Refresh {refresh_num}/2 for '{formatted['title']}' "
                f"({original_board} → {board})"
            )

            # Generate fresh image with a different template
            overlay_path = make_refresh_pin_image(
                formatted["image_url"],
                formatted["title"],
                formatted.get("price"),
                pid,
                refresh_num,
            )

            if not overlay_path:
                logger.warning(f"Image generation failed for {pid}, skipping")
                continue

            content = generate_content_package(formatted, board)

            # Post as a brand new pin (fresh image = fresh content for Pinterest)
            success, pin_id = pinterest.create_pin(
                image_path=overlay_path,
                title=content["pin_title"],
                description=content["pin_description"],
                board_id=board_id,
                url=formatted["url"],
                alt_text=formatted.get("image_alt", ""),
            )

            Path(overlay_path).unlink(missing_ok=True)

            if not success:
                logger.warning(f"Refresh pin post failed for {pid}")
                continue

            # Record in refresh history
            refresh_history["refreshes"].append({
                "product_id": pid,
                "title": formatted["title"],
                "original_board": original_board,
                "board": board,
                "refresh_number": refresh_num,
                "pin_id": pin_id,
                "timestamp": datetime.now().isoformat(),
            })
            save_refresh_history(refresh_history)

            # Also record in main history so daily cap and dedup work correctly
            history["posts"].append({
                "product_id": pid,
                "title": formatted["title"],
                "board": board,
                "is_refresh": True,
                "refresh_number": refresh_num,
                "timestamp": datetime.now().isoformat(),
            })
            save_history(history)

            used_boards_today.add(board)
            refreshed += 1
            logger.info(f"✓ Refresh pin posted (ID: {pin_id})")

            if refreshed < min(len(candidates), MAX_REFRESHES_PER_RUN):
                delay = random.randint(30, 60)
                logger.info(f"Waiting {delay}s...")
                time.sleep(delay)

        logger.info(f"✓ Refresh run complete: {refreshed} pins posted")

    except Exception as e:
        logger.error(f"Refresh error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_refresh_posting()
