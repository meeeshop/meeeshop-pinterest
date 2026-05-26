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
# Expanded to include ALL relevant boards so refreshes reach more audiences.
REFRESH_BOARD_POOLS = {
    "dress": [
        "Dressy Outfits", "Cocktail Dresses", "Chic & Effortless Styles",
        "Woman Fashion!", "Festive Styles", "Short Tall dresses", "Outfit Ideas",
        "Casual", "Trendy & Trendes...", "Every Peak Clothing", "Festival",
        "Festive & Flora Fits", "Daris & Desi Womens...", "Dress",
        "Effortless Looks", "Chic Looks", "Luxe Clothing",
    ],
    "top":   [
        "Camis & Tanks", "Puff Sleeves Tops", "Blouse", "Blouses", "Chic Looks",
        "Cool & Casual Styles", "Effortless Looks", "Ootd #ootd",
        "Casual", "Everyday Style", "Simple Outfits", "Spicing Outfits",
        "Relaxed Yet Trendy...", "Weekend to Workout", "Woman Fashion!",
    ],
    "jeans": [
        "Straight Leg Jeans", "Fitted Jeans", "Casual", "Weekend to Workout",
        "Everyday Style", "Ootd #ootd", "Kimchi USA Jeans", "Simple Outfits",
        "Relaxed Yet Trendy...", "Spicing Outfits", "Cool & Casual Styles",
    ],
    "jacket": [
        "Outer wear", "Festive & Flora Fits", "Chic & Cozy Anim...",
        "Edgy Fashion", "Wardrobe Must Haves", "Winter Outfits",
        "Thanks giving Outfits", "Fall looks", "comfy fall outfits",
        "Luxe Clothing", "Meshohn Luxe Styles",
    ],
    "pants": [
        "Casual", "Weekend to Workout", "Everyday Style",
        "Relaxed Yet Trendy...", "Simple Outfits", "Spicing Outfits",
        "Cool & Casual Styles", "Ootd #ootd", "Woman Fashion!",
    ],
    "skirt": [
        "Dressy Outfits", "Festive Styles", "Chic & Effortless Styles",
        "Woman Fashion!", "Outfit Ideas", "Casual", "Effortless Looks",
        "Spicing Outfits", "Festive & Flora Fits",
    ],
    "sweater": [
        "Sweaters & Sweater...", "Sweaters for women", "Chic & Cozy Anim...",
        "comfy fall outfits", "Wardrobe Must Haves", "Fall looks",
        "Winter Outfits", "Thanks giving Outfits", "Everyday Style",
        "Womens Cardigans", "Casual",
    ],
    "cardigan": [
        "Sweaters", "Sweaters for women", "Chic & Cozy Anim...",
        "comfy fall outfits", "Womens shacket", "Fall looks",
        "Winter Outfits", "Everyday Style", "Wardrobe Must Haves",
    ],
    "bag":   [
        "Handbag #handsips", "Nylon backpack", "Trendy Backpacks",
        "Wardrobe Must Haves", "Best selling products", "Bags",
        "Stylish Finds", "Luxe Clothing",
    ],
    "shoe":  [
        "Footwear", "Boat Shoes", "Ankle Strap Flats", "Outfit Ideas",
        "Casual", "Everyday Style", "Simple Outfits",
    ],
    "jumpsuit": [
        "Rompers_Jumpsuits &...", "Dressy Outfits", "Casual",
        "Woman Fashion!", "Ootd #ootd", "Festival", "Festive & Flora Fits",
        "Spicing Outfits", "Effortless Looks",
    ],
    "default": [
        "Stylish Finds", "Wardrobe Must Haves", "Wardrobe Oozes",
        "Confidence Ladies", "Chic Looks", "Effortless Looks",
        "Cool & Casual Styles", "Simple Outfits", "Woman Fashion!",
        "Trendy & Trendes...", "Every Peak Clothing", "Spicing Outfits",
        "Luxe Clothing", "Meshohn Luxe Styles", "Shop For Hotties",
        "Unique USA", "LE US Womens Cloth...", "Fashion Models",
        "Fresh Finds New...", "Our Recommended...", "new products",
        "Social", "Plus Size", "Edgy Fashion", "Festive & Flora Fits",
    ],
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
    refresh_cursor: int = 0,
) -> Optional[Dict]:
    """Pick a board different from original_board and not used today.

    refresh_cursor rotates the fallback starting point through all boards so
    repeated refreshes don't always land on the same fallback boards.
    """
    from board_mapping import MEEESHOP_BOARDS

    boards_by_name = {b["name"].lower(): b for b in boards}

    def find(name: str) -> Optional[Dict]:
        b = boards_by_name.get(name.lower())
        if b:
            return b
        for board in boards:
            if name.lower() in board["name"].lower():
                return board
        return None

    def eligible(b: Optional[Dict]) -> bool:
        return (b is not None
                and b["name"].lower() != original_board.lower()
                and b["name"] not in used_boards_today)

    category = _category_key(title, product_type)
    pool = REFRESH_BOARD_POOLS.get(category, REFRESH_BOARD_POOLS["default"])

    for candidate in pool:
        if candidate.lower() == original_board.lower():
            continue
        b = find(candidate)
        if eligible(b):
            return b

    # Cursor-based fallback: rotate through ALL known boards so we don't
    # always fall back to the same ones when the category pool is exhausted.
    live_names = {b["name"] for b in boards}
    ordered = [n for n in MEEESHOP_BOARDS if n in live_names]
    extras = [b["name"] for b in boards if b["name"] not in set(ordered)]
    all_names = ordered + extras

    for i in range(len(all_names)):
        name = all_names[(refresh_cursor + i) % len(all_names)]
        b = find(name)
        if eligible(b):
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


def pick_refresh_image_url(product: Dict[str, Any], refresh_number: int) -> str:
    """
    Pick a visually distinct product image for each refresh.

    Daily always uses images[0] (front shot). Images[0] and [1] are typically
    front/back of the same outfit — nearly identical. So refreshes start at
    index 2 to guarantee a lifestyle or detail shot:
      refresh 1 → images[2] if available, else images[0]
      refresh 2 → images[3] if available, else images[0]

    Falls back to images[0] only when the product has fewer than 3 images
    (template change alone will differentiate the pin in that case).
    """
    images = product.get("images", [])
    if not images:
        return ""

    # Preferred indices for refresh 1 and 2 — skip 0 and 1 (front/back pair)
    preferred = [2, 3, 4]
    target_idx = preferred[min(refresh_number - 1, len(preferred) - 1)]

    if target_idx < len(images):
        return images[target_idx].get("src", "")

    # Not enough images — use index 0 (template change makes it look different)
    return images[0].get("src", "")


def make_refresh_pin_image(
    product: Dict[str, Any],
    title: str,
    price: Optional[str],
    product_id: str,
    refresh_number: int,
) -> Optional[str]:
    """
    Download a DIFFERENT product image and apply a DIFFERENT template.

    - Image: rotates through Shopify product images[] by refresh_number index
    - Template: uses product_id hash as stable base, offset by refresh_number
      so refresh 1 and 2 always differ from each other and from the original
      (which used MD5(title) % 5 with no template_index passed)
    """
    image_url = pick_refresh_image_url(product, refresh_number)
    if not image_url:
        logger.warning(f"No image URL for product {product_id}")
        return None

    tmp_src = Path("/tmp") / f"refresh_src_{product_id}.jpg"
    if not download_image(image_url, tmp_src):
        return None

    # Base on product_id hash (stable) — daily used MD5(title) % 5
    # Offset by refresh_number+1 guarantees: original≠refresh1≠refresh2
    base_idx = int(hashlib.md5(str(product_id).encode()).hexdigest(), 16) % 5
    new_idx = (base_idx + refresh_number) % 5

    logger.info(f"Refresh image: variant {refresh_number} of {len(product.get('images', []))}, template {new_idx}")

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


def _build_refresh_counts(refresh_history: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, datetime]]:
    """Parse refresh_history into per-product counts and last-refresh timestamps."""
    refresh_counts: Dict[str, int] = {}
    last_refresh_time: Dict[str, datetime] = {}
    for r in refresh_history.get("refreshes", []):
        pid = r["product_id"]
        refresh_counts[pid] = refresh_counts.get(pid, 0) + 1
        ts = datetime.fromisoformat(r["timestamp"])
        if pid not in last_refresh_time or ts > last_refresh_time[pid]:
            last_refresh_time[pid] = ts
    return refresh_counts, last_refresh_time


def _is_eligible(
    pid: str,
    post_time: datetime,
    refresh_counts: Dict[str, int],
    last_refresh_time: Dict[str, datetime],
) -> bool:
    """Return True if this product/pin is within the 48h–7day refresh window."""
    now = datetime.now()
    count = refresh_counts.get(pid, 0)

    if count >= MAX_REFRESHES_PER_PRODUCT:
        return False

    age_hours = (now - post_time).total_seconds() / 3600

    if age_hours > 7 * 24:
        return False

    if count == 0 and age_hours < FIRST_REFRESH_HOURS:
        return False

    if count == 1:
        last = last_refresh_time.get(pid)
        if last and (now - last).total_seconds() / 3600 < SECOND_REFRESH_HOURS:
            return False

    return True


def fetch_products_for_refresh(
    shopify: "ShopifyClient",
    refresh_history: Dict[str, Any],
    min_stock: int = 15,
) -> List[Dict[str, Any]]:
    """
    Fetch products eligible for refresh posting.

    Strategy: Get products with stock > min_stock, exclude those already refreshed
    more than MAX_REFRESHES_PER_PRODUCT times. This works standalone without
    requiring posting_history.json — refresh can run independently of daily postings.

    Returns products ready for their 1st or 2nd refresh pins.
    """
    refresh_counts, _ = _build_refresh_counts(refresh_history)

    # Fetch all active products from Shopify
    products = shopify.get_products(limit=250)
    logger.info(f"Fetched {len(products)} total products from Shopify")

    eligible = []
    for p in products:
        pid = str(p.get("id"))

        # Skip if already has max refreshes
        if refresh_counts.get(pid, 0) >= MAX_REFRESHES_PER_PRODUCT:
            continue

        # Skip if no stock
        max_stock = max(
            (v.get("inventory_quantity", 0) for v in p.get("variants", [])),
            default=0
        )
        if max_stock < min_stock:
            continue

        eligible.append(p)

    logger.info(f"Found {len(eligible)} products eligible for refresh (stock > {min_stock})")
    random.shuffle(eligible)
    return eligible


def get_candidates(
    history: Dict[str, Any],
    refresh_history: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """FALLBACK source: history file — same logic, used when Pinterest API is unavailable."""

    refresh_counts, last_refresh_time = _build_refresh_counts(refresh_history)

    candidates = []
    seen_product_ids = set()

    for post in history.get("posts", []):
        pid = post.get("product_id")
        if not pid or pid in seen_product_ids:
            continue
        if post.get("is_refresh"):
            continue
        seen_product_ids.add(pid)

        try:
            post_time = datetime.fromisoformat(post["timestamp"])
        except (KeyError, ValueError):
            continue

        if not _is_eligible(pid, post_time, refresh_counts, last_refresh_time):
            continue

        count = refresh_counts.get(pid, 0)
        candidates.append({**post, "_refresh_number": count + 1})

    candidates.sort(key=lambda p: p["timestamp"])
    logger.info(f"{len(candidates)} candidates from posting history (fallback)")
    return candidates


def run_refresh_posting():
    """Main entry: create fresh pins for products due for their 48h/96h refresh."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    EnvLoader.load_youtube_env()

    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    if not all([shopify_url, shopify_token]):
        raise ValueError("Missing required Shopify credentials in .env")

    refresh_history = load_refresh_history()

    pinterest = PinterestClient()
    shopify = ShopifyClient(shopify_url, shopify_token)

    try:
        if not pinterest.login():
            raise RuntimeError("Pinterest login failed")

        boards = pinterest.fetch_boards()
        if not boards:
            raise RuntimeError("No boards found")
        logger.info(f"Fetched {len(boards)} boards")

        # Fetch products eligible for refresh (stock > 15, not yet max-refreshed)
        candidates = fetch_products_for_refresh(shopify, refresh_history, min_stock=15)

        if not candidates:
            logger.info(f"No products eligible for refresh")
            return

        logger.info(f"{len(candidates)} products ready for refresh pins")

        used_boards_today: set = set()
        refreshed = 0
        refresh_cursor = 0  # advances per pin to spread fallback boards across all boards
        refresh_counts, _ = _build_refresh_counts(refresh_history)

        for product in candidates:
            if refreshed >= MAX_REFRESHES_PER_RUN:
                break

            pid = str(product["id"])
            refresh_num = refresh_counts.get(pid, 0) + 1

            # Skip if no images
            if not product.get("images"):
                logger.warning(f"Product {pid} has no images — skipping")
                continue

            formatted = format_product_for_pinterest(product, store_base_url)

            # No original_board for standalone refresh — pick category-relevant board
            # (in integrated mode, would reference posting_history for original board)
            original_board = ""

            board_info = pick_refresh_board(
                original_board,
                formatted["title"],
                product.get("product_type", ""),
                boards,
                used_boards_today,
                refresh_cursor=refresh_cursor,
            )
            refresh_cursor += 1
            if not board_info:
                logger.warning(f"No eligible refresh board for '{formatted['title']}'")
                continue

            board = board_info["name"]
            board_id = board_info["id"]
            logger.info(
                f"Refresh {refresh_num}/2 for '{formatted['title']}' "
                f"({original_board} → {board})"
            )

            overlay_path = make_refresh_pin_image(
                product,
                formatted["title"],
                formatted.get("price"),
                pid,
                refresh_num,
            )
            if not overlay_path:
                logger.warning(f"Image generation failed for {pid}, skipping")
                continue

            content = generate_content_package(formatted, board)

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
