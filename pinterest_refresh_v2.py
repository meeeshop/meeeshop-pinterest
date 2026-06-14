"""
pinterest_refresh_v2.py — Phase 2 refresh strategy

Changes from V1:
  - MAX_REFRESHES_PER_WINDOW: 8 → 4  (quality over quantity)
  - Uses content_generator_v2 (USA-targeted content)
  - History file: refresh_history_v2.json (separate from V1)
  - Staging file: refresh_staging_v2.json
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
from content_generator_v2 import generate_content_package   # ← V2 content
from video_picker import EnvLoader
from image_overlay import add_text_overlay, PIN_W, PIN_H
from board_mapping import MEEESHOP_BOARDS, CATEGORY_TO_BOARDS

logger = logging.getLogger(__name__)

REFRESH_HISTORY_FILE = Path(__file__).parent / "refresh_history_v2.json"
REFRESH_STAGING_FILE = Path(__file__).parent / "refresh_staging_v2.json"

REFRESH_WINDOW_2_DAYS   = 2
REFRESH_WINDOW_4_7_DAYS = (4, 7)
MAX_REFRESHES_PER_WINDOW = 4   # V2: 4 (was 8) — fewer, higher-quality repins
INACTIVE_BOARD_THRESHOLD_DAYS = 14  # Mark boards with no new pins in 14 days as inactive

REFRESH_BOARD_POOLS = {
    "dress": [
        "Dressy Outfits", "Cocktail Dresses", "Chic & Effortless Styles",
        "Woman Fashion!", "Festive Styles", "Short Tall dresses", "Outfit Ideas",
        "Casual", "Trendy & Trendes...", "Every Peak Clothing", "Festival",
        "Festive & Flora Fits", "Daris & Desi Womens...", "Dress",
        "Effortless Looks", "Chic Looks", "Luxe Clothing",
    ],
    "top": [
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
    "bag": [
        "Handbag #handsips", "Nylon backpack", "Trendy Backpacks",
        "Wardrobe Must Haves", "Best selling products", "Bags",
        "Stylish Finds", "Luxe Clothing",
    ],
    "shoe": [
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


def load_refresh_history() -> Dict[str, Any]:
    if REFRESH_HISTORY_FILE.exists():
        return json.loads(REFRESH_HISTORY_FILE.read_text(encoding="utf-8"))
    return {"refreshes": []}


def save_refresh_history(rh: Dict[str, Any]):
    REFRESH_HISTORY_FILE.write_text(json.dumps(rh, indent=2, default=str), encoding="utf-8")


def _category_key(title: str, product_type: str = "") -> str:
    import re
    text = f"{title} {product_type}".lower()
    
    category_mappings = [
        (["backpack", "bag", "purse", "tote", "handbag", "crossbody", "clutch", "satchel", "wallet", "pouch", "duffel", "hobo"], "bag"),
        (["dress", "gown", "midi", "maxi", "mini"], "dress"),
        (["top", "blouse", "tank", "shirt", "cami"], "top"),
        (["jeans", "denim", "pants", "legging"], "pants"),
        (["jacket", "coat", "shacket", "blazer"], "jacket"),
        (["cardigan"], "cardigan"),
        (["sweater", "knit", "pullover"], "sweater"),
        (["skirt"], "skirt"),
        (["shoe", "boot", "flat", "heel", "sandal"], "shoe"),
        (["jumpsuit", "romper"], "jumpsuit")
    ]
    
    boundary_keys = {"top", "flat"}
    
    for keywords, category_key in category_mappings:
        for kw in keywords:
            if kw in boundary_keys:
                if kw == "top":
                    if re.search(r'\btops?(?!-handle|-loading|-heavy)\b', text):
                        return category_key
                else:
                    if re.search(r'\b' + re.escape(kw) + r's?\b', text):
                        return category_key
            else:
                if kw in text:
                    return category_key
    return "default"


def _get_refresh_window(timestamp: datetime) -> Optional[str]:
    now = datetime.now()
    age_days = (now - timestamp).total_seconds() / (24 * 3600)
    if age_days <= REFRESH_WINDOW_2_DAYS:
        return "2day"
    if REFRESH_WINDOW_4_7_DAYS[0] <= age_days <= REFRESH_WINDOW_4_7_DAYS[1]:
        return "4-7day"
    return None


def _build_boards_used(refresh_history: Dict[str, Any]) -> Dict[str, set]:
    boards_used: Dict[str, set] = {}
    for r in refresh_history.get("refreshes", []):
        pid = r.get("product_id")
        if not pid:
            continue
        boards_used.setdefault(pid, set()).add(r.get("board", ""))
    return boards_used


def download_image(url: str, save_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        logger.error(f"Image download failed: {e}")
        return False


def pick_refresh_image_url(product: Dict[str, Any], window: str) -> str:
    images = product.get("images", [])
    if not images:
        return ""
    window_indices = {"2day": [2, 3], "4-7day": [4, 5]}
    for idx in window_indices.get(window, [0]):
        if idx < len(images):
            return images[idx].get("src", "")
    return images[0].get("src", "") if images else ""


def make_refresh_pin_image(
    product: Dict[str, Any],
    title: str,
    price: Optional[str],
    product_id: str,
    window: str,
) -> Optional[str]:
    image_url = pick_refresh_image_url(product, window)
    if not image_url:
        logger.warning(f"No image URL for product {product_id}")
        return None

    tmp_src = Path("/tmp") / f"refresh_src_{product_id}.jpg"
    if not download_image(image_url, tmp_src):
        return None

    base_idx = int(hashlib.md5(str(product_id).encode()).hexdigest(), 16) % 5
    window_offset = {"2day": 1, "4-7day": 2}.get(window, 0)
    new_idx = (base_idx + window_offset) % 5

    out_path = Path("/tmp") / f"refresh_overlay_{product_id}_{window}.jpg"
    result = add_text_overlay(
        str(tmp_src),
        title=title,
        price=price,
        output_path=str(out_path),
        template_index=new_idx,
    )

    tmp_src.unlink(missing_ok=True)
    return result if result else None


def pick_refresh_board(
    title: str,
    product_type: str,
    boards: List[Dict],
    boards_already_used: set,
    used_boards_today: set,
    refresh_cursor: int = 0,
    inactive_boards: Optional[List[str]] = None,
) -> Optional[Dict]:
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
                and b["name"] not in boards_already_used
                and b["name"] not in used_boards_today)

    category = _category_key(title, product_type)
    pool = REFRESH_BOARD_POOLS.get(category, REFRESH_BOARD_POOLS["default"])

    inactive_set = {name.lower() for name in (inactive_boards or [])}

    # 1. Prioritize inactive boards from the category-specific pool
    if inactive_set:
        for candidate in pool:
            if candidate.lower() in inactive_set:
                b = find(candidate)
                if eligible(b):
                    logger.info(f"[Inactive Board Priority] Prioritizing inactive pool board: '{b['name']}'")
                    return b

    # 2. Try normal eligible boards from the pool
    for candidate in pool:
        b = find(candidate)
        if eligible(b):
            return b

    # 3. Fallback to existing generic/default boards before creating a new one
    if category != "default":
        logger.info(f"No eligible board in '{category}' pool; checking generic boards from 'default' pool...")
        default_pool = REFRESH_BOARD_POOLS["default"]
        for candidate in default_pool:
            b = find(candidate)
            if eligible(b):
                logger.info(f"Using existing generic fallback board: '{b['name']}'")
                return b

    # 4. If no relevant category or generic board from pools is eligible, fallback to custom generic board "Meeeshop Shopping"
    generic_name = "Meeeshop Shopping"
    b_generic = find(generic_name)
    if b_generic:
        if eligible(b_generic):
            logger.info(f"Using existing generic board: '{b_generic['name']}'")
            return b_generic
        else:
            # Already used today or already pinned for this product
            logger.warning(f"Generic board '{generic_name}' already used/ineligible.")
            if b_generic["name"] not in boards_already_used:
                logger.info(f"Using generic board '{generic_name}' (ignoring used_boards_today restriction as fallback)")
                return b_generic

    # If the generic board doesn't exist, or exists but is already used for this product, return representing creation is needed
    return {
        "id": "CREATE_GENERIC",
        "name": generic_name,
        "url": ""
    }



def _parse_pin_timestamp(pin: Dict[str, Any]) -> Optional[datetime]:
    raw = pin.get("created_at", "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00").split("+")[0])
    except Exception:
        return None


def fetch_pins_in_window(
    pinterest: PinterestClient,
    boards: List[Dict],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    now = datetime.now()
    cutoff_old = now - timedelta(days=7)

    pins_2day: List[Dict[str, Any]] = []
    pins_4_7day: List[Dict[str, Any]] = []
    inactive_boards: List[str] = []
    staged: List[Dict[str, Any]] = []
    sample_logged = False
    no_ts_count = 0

    for board in boards:
        board_name = board.get("name", "")
        board_id = board.get("id", "")

        logger.info(f"Scanning board: {board_name}")
        pins = pinterest.fetch_board_pins(board_id, board_name)

        if pins and not sample_logged:
            sample = pins[0]
            logger.info(f"[debug] Sample pin keys: {list(sample.keys())}")
            logger.info(f"[debug] Sample pin created_at={sample.get('created_at')!r}")
            sample_logged = True

        # Check for board inactivity/few pins
        is_inactive = False
        if not pins:
            is_inactive = True
            logger.info(f"  Board '{board_name}' is inactive (0 pins)")
        else:
            newest_ts = _parse_pin_timestamp(pins[0])
            if newest_ts is not None:
                age_days = (now - newest_ts).total_seconds() / (24 * 3600)
                if age_days >= INACTIVE_BOARD_THRESHOLD_DAYS:
                    is_inactive = True
                    logger.info(f"  Board '{board_name}' is inactive (newest pin age: {age_days:.1f} days)")
            if len(pins) < 5:
                is_inactive = True
                logger.info(f"  Board '{board_name}' has few pins ({len(pins)} pins) (marked inactive)")

        if is_inactive:
            inactive_boards.append(board_name)

        board_window_count = {"2day": 0, "4-7day": 0}
        for idx, pin in enumerate(pins):
            ts = _parse_pin_timestamp(pin)
            if ts is None:
                no_ts_count += 1
                estimated_age_days = idx / 20.0
                ts = now - timedelta(days=estimated_age_days)

            if ts < cutoff_old:
                break

            window = _get_refresh_window(ts)
            if window is None:
                continue

            pin_data = {
                **pin,
                "board": board_name,
                "board_id": board_id,
                "window": window,
                "age_hours": round((now - ts).total_seconds() / 3600, 1),
            }

            if window == "2day":
                pins_2day.append(pin_data)
                board_window_count["2day"] += 1
            else:
                pins_4_7day.append(pin_data)
                board_window_count["4-7day"] += 1

            staged.append(pin_data)

        if any(board_window_count.values()):
            logger.info(
                f"  Board '{board_name}': "
                f"{board_window_count['2day']} 2-day, "
                f"{board_window_count['4-7day']} 4-7-day"
            )

    if no_ts_count:
        logger.warning(f"[debug] {no_ts_count} pins had no created_at — used position fallback")

    logger.info(f"[V2] Total qualifying pins — 2-day: {len(pins_2day)}, 4-7-day: {len(pins_4_7day)}")
    logger.info(f"[V2] Total inactive boards identified: {len(inactive_boards)}")

    REFRESH_STAGING_FILE.write_text(
        json.dumps(
            {"scanned_at": now.isoformat(), "pins_2day": pins_2day, "pins_4_7day": pins_4_7day},
            indent=2, default=str,
        ),
        encoding="utf-8",
    )

    return pins_2day, pins_4_7day, inactive_boards


def run_refresh_posting():
    """Refresh posting — V2: max 4 per window (was 8), uses V2 content."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    EnvLoader.load_youtube_env()

    shopify_url   = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    if not all([shopify_url, shopify_token]):
        raise ValueError("Missing required Shopify credentials")

    refresh_history = load_refresh_history()
    refreshed_recently = set()
    now = datetime.now()
    four_days_ago = now - timedelta(days=4)
    for r in refresh_history.get("refreshes", []):
        ts_str = r.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts > four_days_ago:
                    refreshed_recently.add(str(r.get("product_id")))
            except Exception:
                pass
    boards_used_per_product = _build_boards_used(refresh_history)

    pinterest = PinterestClient()
    shopify   = ShopifyClient(shopify_url, shopify_token)

    try:
        if not pinterest.login():
            raise RuntimeError("Pinterest login failed")

        boards = pinterest.fetch_boards()
        if not boards:
            raise RuntimeError("No boards found")
        logger.info(f"Fetched {len(boards)} boards")

        pins_2day, pins_4_7day, inactive_boards = fetch_pins_in_window(pinterest, boards)
        if not pins_2day and not pins_4_7day:
            logger.warning("No pins found in windows — nothing to refresh")
            return

        total_refreshed = 0
        window_pin_map = {"2day": pins_2day, "4-7day": pins_4_7day}

        for window in ["2day", "4-7day"]:
            logger.info(f"\n{'='*60}")
            logger.info(f"[V2] Processing {window} window (max {MAX_REFRESHES_PER_WINDOW} pins)...")
            logger.info(f"{'='*60}")

            window_pins = window_pin_map[window]
            used_boards_today: set = set()
            window_refreshed = 0
            refresh_cursor = 0
            seen_products = set()

            for pin in window_pins:
                if window_refreshed >= MAX_REFRESHES_PER_WINDOW:
                    logger.info(f"Reached max per window ({MAX_REFRESHES_PER_WINDOW})")
                    break

                product_link = pin.get("link", "")
                if not product_link or "meeeshop" not in product_link.lower():
                    continue

                try:
                    parts = product_link.split("/products/")
                    if len(parts) < 2:
                        continue
                    product_handle = parts[1].split("?")[0].strip("/")
                    product = shopify.get_product_by_handle(product_handle)
                    if not product:
                        logger.warning(f"Product not found: {product_handle}")
                        continue
                except Exception as e:
                    logger.warning(f"Failed to extract product from {product_link}: {e}")
                    continue

                product_id = str(product.get("id", ""))
                if not product_id or product_id in seen_products:
                    continue
                seen_products.add(product_id)

                # Check 4-day block rule
                if product_id in refreshed_recently:
                    logger.info(f"Skipping product {product_id} ('{product.get('title', '')}') - already refreshed within last 4 days")
                    continue

                if not product.get("images"):
                    logger.warning(f"Product {product_id} has no images — skipping")
                    continue

                formatted = format_product_for_pinterest(product, store_base_url)
                original_board = pin.get("board", "")
                boards_used_for_product = boards_used_per_product.get(product_id, set()).copy()
                if original_board:
                    boards_used_for_product.add(original_board)

                board_info = pick_refresh_board(
                    formatted["title"],
                    product.get("product_type", ""),
                    boards,
                    boards_already_used=boards_used_for_product,
                    used_boards_today=used_boards_today,
                    refresh_cursor=refresh_cursor,
                    inactive_boards=inactive_boards,
                )
                refresh_cursor += 1

                if not board_info:
                    logger.info(f"✗ No {window} board for '{formatted['title']}' — skipping")
                    continue

                if board_info.get("id") == "CREATE_GENERIC":
                    # Dynamically look up or create generic board
                    existing_board = pinterest.get_board_by_name("Meeeshop Shopping")
                    if existing_board:
                        board_info = existing_board
                    else:
                        success, new_board_data = pinterest.create_board(
                            name="Meeeshop Shopping",
                            description="Trending shopping finds from Meeeshop."
                        )
                        if success and new_board_data:
                            board_info = new_board_data
                            boards.append(new_board_data)
                            logger.info(f"Dynamically created generic board: '{board_info['name']}'")
                        else:
                            logger.error("Failed to create generic board, skipping")
                            continue

                new_board = board_info["name"]
                board_id  = board_info["id"]
                logger.info(f"✓ {window} repin: '{formatted['title']}' ({original_board} → {new_board})")

                overlay_path = make_refresh_pin_image(
                    product, formatted["title"], formatted.get("price"), product_id, window
                )
                if not overlay_path:
                    logger.warning(f"Image generation failed for {product_id}, skipping")
                    continue

                content = generate_content_package(formatted, new_board)

                success, pin_id = pinterest.create_pin(
                    image_path=overlay_path,
                    title=content["pin_title"],
                    description=content["pin_description"],
                    board_id=board_id,
                    url=formatted["url"],
                    alt_text=content.get("pin_alt_text") or formatted.get("image_alt", ""),
                )

                Path(overlay_path).unlink(missing_ok=True)

                if not success:
                    logger.warning(f"Refresh pin post failed for {product_id}")
                    continue

                refresh_history["refreshes"].append({
                    "product_id": product_id,
                    "title": formatted["title"],
                    "original_board": original_board,
                    "board": new_board,
                    "window": window,
                    "pin_id": pin_id,
                    "timestamp": datetime.now().isoformat(),
                })
                save_refresh_history(refresh_history)
                boards_used_per_product.setdefault(product_id, set()).add(new_board)

                used_boards_today.add(new_board)
                window_refreshed += 1
                total_refreshed += 1

                if window_refreshed < len(window_pins):
                    delay = random.randint(30, 60)
                    logger.info(f"Waiting {delay}s...")
                    time.sleep(delay)

            logger.info(f"[V2] ✓ {window} window complete: {window_refreshed} pins posted")

        logger.info(f"\n[V2] ✓ Refresh run complete: {total_refreshed} total pins posted")

    except Exception as e:
        logger.error(f"Refresh error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_refresh_posting()
