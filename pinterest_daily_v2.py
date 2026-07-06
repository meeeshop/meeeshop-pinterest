"""
pinterest_daily_v2.py — Phase 2 daily Pinterest orchestrator

Changes from V1:
  - MAX_PINS_PER_DAY: 16 → 8  (safe re-activation limit for dormant account)
  - PINS_PER_RUN: 4 → 2       (2 pins × 4 runs = 8/day)
  - Uses content_generator_v2 (USA keywords, search-first titles, longer descriptions)
  - History file: posting_history_v2.json (separate from V1 — no conflicts)
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
from content_generator_v2 import generate_content_package   # ← V2 content
from video_picker import EnvLoader
from image_overlay import add_text_overlay

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "posting_history_v2.json"
MAX_PINS_PER_DAY = 8     # V2: 2 runs × 4 slots — safe for re-activation
PINS_PER_RUN    = 2      # V2: 2 pins per run (was 4)


def load_history() -> Dict[str, Any]:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {
        "posts": [], "board_last_used": {}, "daily_count": 0,
        "last_post_time": None, "board_rotation_cursor": 0,
    }


def advance_board_cursor(history: Dict[str, Any], steps: int, total_boards: int) -> int:
    cursor = history.get("board_rotation_cursor", 0) % max(total_boards, 1)
    history["board_rotation_cursor"] = (cursor + steps) % total_boards
    return cursor


def save_history(history: Dict[str, Any]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def reset_daily_count():
    history = load_history()
    last_post = history.get("last_post_time")
    if last_post:
        last_post_date = datetime.fromisoformat(last_post).date()
        if last_post_date != datetime.now().date():
            history["daily_count"] = 0
            save_history(history)
    return history


def can_post_today(history: Dict[str, Any]) -> bool:
    if history["daily_count"] >= MAX_PINS_PER_DAY:
        logger.warning(f"Daily limit ({MAX_PINS_PER_DAY}) reached")
        return False
    return True


def download_image(url: str, save_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        logger.info(f"Downloaded image: {save_path.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False


def post_pin(
    client: PinterestClient,
    product_data: Dict[str, Any],
    board_id: str,
    content: Dict[str, Any],
) -> bool:
    image_file = Path("/tmp") / f"pin_{product_data['product_id']}.jpg"
    if not download_image(product_data["image_url"], image_file):
        logger.error(f"Failed to download image for pin: {content['pin_title']}")
        return False

    additional_image_files = []
    overlay_image = None
    try:
        # Download up to 3 additional images for collages
        all_image_urls = product_data.get("all_image_urls", [])
        extra_urls = [url for url in all_image_urls if url != product_data["image_url"]][:3]
        for idx, url in enumerate(extra_urls):
            temp_img_file = Path("/tmp") / f"pin_extra_{product_data['product_id']}_{idx}.jpg"
            if download_image(url, temp_img_file):
                additional_image_files.append(temp_img_file)

        overlay_file = Path("/tmp") / f"pin_overlay_{product_data['product_id']}.jpg"
        overlay_image = add_text_overlay(
            str(image_file),
            title=content["pin_title"],
            cta="Shop Now",
            price=product_data.get("price"),
            output_path=str(overlay_file),
            additional_image_paths=[str(p) for p in additional_image_files],
        )

        if not overlay_image:
            logger.warning("Image overlay failed, posting without overlay")
            overlay_image = str(image_file)

        logger.info(f"Creating pin: {content['pin_title']}")
        time.sleep(2)

        success, pin_id = client.create_pin(
            image_path=overlay_image,
            title=content["pin_title"],
            description=content["pin_description"],
            board_id=board_id,
            url=product_data["url"],
            alt_text=content.get("pin_alt_text") or product_data.get("image_alt", ""),
        )

        if success:
            logger.info(f"✓ Posted: {content['pin_title']} (ID: {pin_id})")
            return True
        else:
            logger.error(f"✗ Failed: {content['pin_title']} — {pin_id}")
            return False

    except Exception as e:
        logger.error(f"Exception creating pin: {e}", exc_info=True)
        return False
    finally:
        image_file.unlink(missing_ok=True)
        if overlay_image and Path(overlay_image).exists() and overlay_image != str(image_file):
            Path(overlay_image).unlink(missing_ok=True)
        for f in additional_image_files:
            f.unlink(missing_ok=True)


def pick_board(
    index: int,
    boards: List[Dict],
    used_boards: set,
    formatted: Dict[str, Any],
    run_board_pool: List[str],
) -> Optional[Dict]:
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
        import re
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
        for keywords, category_key_val in category_mappings:
            for kw in keywords:
                if kw in boundary_keys:
                    if kw == "top":
                        if re.search(r'\btops?(?!-handle|-loading|-heavy)\b', text):
                            return category_key_val
                    else:
                        if re.search(r'\b' + re.escape(kw) + r's?\b', text):
                            return category_key_val
                else:
                    if kw in text:
                        return category_key_val
        return "default"

    search = f"{formatted.get('title','').lower()} {formatted.get('product_type','').lower()}"
    cat = category_key(search)

    if cat != "default":
        for board_name in CATEGORY_TO_BOARDS.get(cat, []):
            b = find(board_name)
            if b and b["name"] not in used_boards:
                return b

    for i in range(len(run_board_pool)):
        candidate = run_board_pool[(index + i) % len(run_board_pool)]
        b = find(candidate)
        if b and b["name"] not in used_boards:
            return b

    available = [b for b in boards if b["name"] not in used_boards]
    return random.choice(available) if available else random.choice(boards)


def fetch_all_eligible_products(
    shopify: "ShopifyClient",
    history: Dict[str, Any],
    min_stock: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch ALL active products with stock > min_stock, paginated via GraphQL.

    Excludes products posted in the last 10 days to ensure diversity.
    Returns products in random order ready for posting.
    """
    products = shopify.get_all_products(status="active")
    logger.info(f"Fetched {len(products)} total products from Shopify")

    ten_days_ago = datetime.now() - timedelta(days=10)
    recent_ids = set()
    for p in history.get("posts", []):
        ts_str = p.get("timestamp")
        if ts_str:
            try:
                ts_str_clean = ts_str.replace("Z", "+00:00")
                ts = datetime.fromisoformat(ts_str_clean)
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                if ts > ten_days_ago:
                    recent_ids.add(str(p.get("product_id")))
            except Exception:
                pass

    # Load other history files to avoid duplicates
    other_histories = [
        ("refresh_history_v2.json", "refreshes", "timestamp"),
        ("video_posting_history.json", "posts", "posted_at"),
        ("blog_posting_history.json", "posts", "timestamp")
    ]
    for filename, list_key, time_key in other_histories:
        history_path = Path(__file__).parent / filename
        if history_path.exists():
            try:
                hist_data = json.loads(history_path.read_text(encoding="utf-8"))
                for item in hist_data.get(list_key, []):
                    ts_str = item.get(time_key)
                    if ts_str:
                        try:
                            # Normalize Z suffix to offset for python fromisoformat
                            ts_str_clean = ts_str.replace("Z", "+00:00")
                            ts = datetime.fromisoformat(ts_str_clean)
                            # Remove timezone info for comparison with local/naive datetime
                            if ts.tzinfo is not None:
                                ts = ts.replace(tzinfo=None)
                            if ts > ten_days_ago:
                                item_id = item.get("product_id") or item.get("id")
                                if item_id:
                                    recent_ids.add(str(item_id))
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Failed to read {filename}: {e}")

    eligible = [
        p for p in products
        if str(p.get("id")) not in recent_ids
        and any(v.get("inventory_quantity", 0) >= min_stock for v in p.get("variants", []))
    ]

    logger.info(f"Eligible products (stock>{min_stock}, not in last 10 days in posts/refreshes): {len(eligible)}")
    random.shuffle(eligible)
    return eligible


def build_run_board_pool(
    all_boards: List[Dict],
    history: Dict[str, Any],
    pins_this_run: int,
) -> List[str]:
    from board_mapping import MEEESHOP_BOARDS, PRIORITY_BOARDS

    live_names = {b["name"] for b in all_boards}
    ordered = [n for n in MEEESHOP_BOARDS if n in live_names]
    extras = [b["name"] for b in all_boards if b["name"] not in set(ordered)]
    all_names = ordered + extras

    if not all_names:
        return [b["name"] for b in all_boards]

    priority_cursor = history.get("board_rotation_cursor", 0) % len(PRIORITY_BOARDS)
    priority_pick = PRIORITY_BOARDS[priority_cursor % len(PRIORITY_BOARDS)]

    fill_count = max(pins_this_run - 1, 1)
    cursor = advance_board_cursor(history, fill_count, len(all_names))

    pool = [priority_pick]
    for i in range(fill_count):
        name = all_names[(cursor + i) % len(all_names)]
        if name not in pool:
            pool.append(name)

    logger.info(f"[V2] Board pool ({len(pool)} boards, cursor {cursor}/{len(all_names)}): {pool}")
    return pool


def run_daily_posting(use_video: bool = False):
    """Post PINS_PER_RUN pins per run (V2: 2 pins × 4 runs = 8/day)."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    EnvLoader.load_youtube_env()
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        logger.info("=" * 60)
        logger.info("[DRY RUN MODE ENABLED] No boards will be created, no pins will be posted, and no history files will be modified.")
        logger.info("=" * 60)

    pinterest_email = get_secret("PINTEREST_EMAIL")
    pinterest_password = get_secret("PINTEREST_PASSWORD")
    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    if not all([pinterest_email, pinterest_password, shopify_url, shopify_token]):
        raise ValueError("Missing required credentials in .env")

    target = int(os.getenv("PINS_TO_POST", str(PINS_PER_RUN)))
    logger.info(f"[V2] Daily run starting — target: {target} pins (daily cap: {MAX_PINS_PER_DAY})")

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
        save_history(history)

        pool = fetch_all_eligible_products(shopify, history, min_stock=15)
        if not pool:
            logger.warning("No eligible products — skipping execution to avoid spam.")
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

            if dry_run:
                logger.info(f"  [DRY RUN] Would download and design pin image for product {product['id']}")
                logger.info(f"  [DRY RUN] Would generate AI title/description for board '{board}'")
                logger.info(f"  [DRY RUN] Would create pin on board '{board}' (ID: {board_id}) with URL '{formatted['url']}'")
                used_boards.add(board)
                posted += 1
                continue

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

        logger.info(f"[V2] ✓ Done: {posted}/{target} pins posted")

    except Exception as e:
        logger.error(f"Daily posting error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_daily_posting()
