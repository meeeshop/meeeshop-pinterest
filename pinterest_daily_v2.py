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
from typing import List, Dict, Any, Optional, Tuple

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest
from content_generator_v2 import generate_content_package   # ← V2 content
from video_picker import EnvLoader
from image_overlay import add_text_overlay
from daily_pin_tracker import DailyPinTracker

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
    board_name: str,
    content: Dict[str, Any],
    last_style: Optional[str] = None,
    last_template: Optional[int] = None,
) -> Tuple[bool, Optional[str], Optional[int]]:
    from image_overlay import get_next_style_and_template

    image_file = Path("/tmp") / f"pin_{product_data['product_id']}.jpg"
    if not download_image(product_data["image_url"], image_file):
        logger.error(f"Failed to download image for pin: {content['pin_title']}")
        return False, None, None

    additional_image_files = []
    overlay_image = None

    # Compute next style & template for strict alternating rotation
    style_used, template_used = get_next_style_and_template(
        last_style=last_style,
        last_template=last_template,
        board_name=board_name,
        title=content["pin_title"],
    )

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
            template_index=template_used,
            additional_image_paths=[str(p) for p in additional_image_files],
            board_name=board_name,
            image_style=style_used,
        )


        if not overlay_image:
            logger.warning("Image overlay failed, posting without overlay")
            overlay_image = str(image_file)

        logger.info(f"Creating pin (Style: {style_used}, Template: {template_used}): {content['pin_title']}")
        time.sleep(2)

        # Route carousel style to video slideshow pin (FFmpeg stitches 4 styled cards into MP4)
        if style_used == "carousel":
            from image_overlay import generate_carousel_card_set
            carousel_cards = generate_carousel_card_set(
                product_image_path=str(image_file),
                title=content["pin_title"],
                category=board_name,
                price=product_data.get("price"),
                cta="Shop Now",
                output_dir="/tmp",
                template_index=template_used,
                additional_image_paths=[str(p) for p in additional_image_files],
                board_name=board_name,
            )

            if len(carousel_cards) > 1:
                success, pin_id = client.create_video_slideshow_pin(
                    image_paths=carousel_cards,
                    title=content["pin_title"],
                    description=content["pin_description"],
                    board_id=board_id,
                    url=product_data["url"],
                    alt_text=content.get("pin_alt_text") or product_data.get("image_alt", ""),
                )
            else:
                success, pin_id = client.create_pin(
                    image_path=overlay_image,
                    title=content["pin_title"],
                    description=content["pin_description"],
                    board_id=board_id,
                    url=product_data["url"],
                    alt_text=content.get("pin_alt_text") or product_data.get("image_alt", ""),
                )
        else:
            success, pin_id = client.create_pin(
                image_path=overlay_image,
                title=content["pin_title"],
                description=content["pin_description"],
                board_id=board_id,
                url=product_data["url"],
                alt_text=content.get("pin_alt_text") or product_data.get("image_alt", ""),
            )


        if success:
            logger.info(f"✓ Posted ({style_used}): {content['pin_title']} (ID: {pin_id})")
            return True, style_used, template_used
        else:
            logger.error(f"✗ Failed ({style_used}): {content['pin_title']} — {pin_id}")
            return False, None, None


    except Exception as e:
        logger.error(f"Exception creating pin: {e}", exc_info=True)
        return False, None, None
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
    history: Dict[str, Any] = None,
) -> Optional[Dict]:
    from board_mapping import select_best_lru_board

    title = formatted.get("title", "")
    ptype = formatted.get("product_type", "")
    last_used = (history or {}).get("board_last_used", {})

    # Select best live board matching category and LRU usage
    return select_best_lru_board(
        product_title=title,
        product_type=ptype,
        live_boards=boards,
        board_last_used=last_used,
        used_boards_in_run=used_boards,
    )




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

    logger.info(
        f"[V2] Multi-board pool initialized across {len(all_names)} active boards (rotation cursor: {cursor})"
    )
    return pool



def get_product_main_category(title: str, product_type: str = "", tags: str = "") -> str:
    """Classify product into core category to enforce rotation across consecutive pins."""
    import re
    text = f"{title} {product_type} {tags}".lower()
    if re.search(r'\b(bag|backpack|purse|tote|handbag|crossbody|clutch|satchel|wallet|pouch|duffel|hobo)\b', text):
        return "bags"
    elif re.search(r'\b(dress|gown|midi|maxi|mini|tie-back|spaghetti)\b', text):
        return "dresses"
    elif re.search(r'\b(jumpsuit|romper|playsuit|overalls|cami jumpsui|jumpsui)\b', text):
        return "jumpsuits"
    elif re.search(r'\b(top|blouse|shirt|cami|tank|tee|sweatshirt|wallflower|wrap top|crop)\b', text):
        return "tops"
    elif re.search(r'\b(jeans|denim|pants|legging|leggings|chino|shorts|bottom|wide leg|trousers|cargo)\b', text):
        return "bottoms"
    elif re.search(r'\b(jacket|coat|shacket|blazer|cardigan|outerwear|vest)\b', text):
        return "outerwear"
    elif re.search(r'\b(sweater|knit|pullover|french terry)\b', text):
        return "sweaters"
    elif re.search(r'\b(skirt)\b', text):
        return "skirts"
    elif re.search(r'\b(shoe|flats|boots|sneakers|sandals|heels)\b', text):
        return "shoes"
    else:
        return "general"


def fetch_all_eligible_products(
    shopify: "ShopifyClient",
    history: Dict[str, Any],
    min_stock: int = 1,
) -> List[Dict[str, Any]]:
    """Fetch ALL active products with stock >= min_stock.

    Uses category-aware cooldowns:
    - Abundant categories (>15 items, e.g. bags): 7-day cooldown
    - Rare categories (<=15 items, e.g. dresses, outerwear, tops): 1-day (24h) cooldown
    Guarantees non-bag categories remain eligible every single day!
    """
    products = shopify.get_all_products(status="active")
    logger.info(f"Fetched {len(products)} total products from Shopify")

    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    one_day_ago = now - timedelta(days=1)

    cat_counts = {}
    for p in products:
        cat = get_product_main_category(p.get("title", ""), p.get("product_type", ""), p.get("tags", ""))
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    recent_ids = set()
    for p in history.get("posts", []):
        ts_str = p.get("timestamp")
        p_id = str(p.get("product_id") or p.get("id") or "")
        p_cat = p.get("category", "general")

        cooldown_cutoff = seven_days_ago if cat_counts.get(p_cat, 0) > 15 else one_day_ago

        if ts_str and p_id:
            try:
                ts_clean = ts_str.replace("Z", "+00:00")
                ts = datetime.fromisoformat(ts_clean)
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                if ts > cooldown_cutoff:
                    recent_ids.add(p_id)
            except Exception:
                pass

    # Load other history files
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
                    item_id = str(item.get("product_id") or item.get("id") or "")
                    item_cat = item.get("category", "general")
                    cooldown_cutoff = seven_days_ago if cat_counts.get(item_cat, 0) > 15 else one_day_ago

                    if ts_str and item_id:
                        try:
                            ts_clean = ts_str.replace("Z", "+00:00")
                            ts = datetime.fromisoformat(ts_clean)
                            if ts.tzinfo is not None:
                                ts = ts.replace(tzinfo=None)
                            if ts > cooldown_cutoff:
                                recent_ids.add(item_id)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Failed to read {filename}: {e}")

    eligible = [
        p for p in products
        if str(p.get("id")) not in recent_ids
        and any(v.get("inventory_quantity", 0) >= min_stock for v in p.get("variants", []))
    ]

    logger.info(f"Eligible products (category-aware cooldown): {len(eligible)} across categories: {[get_product_main_category(p.get('title',''), p.get('product_type',''), p.get('tags','')) for p in eligible]}")
    random.shuffle(eligible)
    return eligible


def select_next_product_lru(
    pool: List[Dict[str, Any]],
    used_indices: set,
    history: Dict[str, Any]
) -> Optional[int]:
    """Select next candidate product prioritizing least-recently-used categories."""
    category_last_used = history.get("category_last_used", {})

    unused_by_cat = {}
    for idx, prod in enumerate(pool):
        if idx in used_indices:
            continue
        cat = get_product_main_category(prod.get("title", ""), prod.get("product_type", ""), prod.get("tags", ""))
        if cat not in unused_by_cat:
            unused_by_cat[cat] = []
        unused_by_cat[cat].append(idx)

    if not unused_by_cat:
        return None

    def cat_sort_key(cat_name: str):
        last_ts = category_last_used.get(cat_name)
        if not last_ts:
            return datetime.min
        try:
            return datetime.fromisoformat(last_ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.min

    sorted_cats = sorted(unused_by_cat.keys(), key=cat_sort_key)
    best_cat = sorted_cats[0]
    candidate_indices = unused_by_cat[best_cat]
    selected_idx = random.choice(candidate_indices)
    logger.info(f"[Category LRU Rotation] Selected '{best_cat}' (Rank 1/LRU out of available categories: {sorted_cats})")
    return selected_idx


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

    logger.info(
        f"[V2] Multi-board pool initialized across {len(all_names)} active boards (rotation cursor: {cursor})"
    )
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

    try:
        pinterest_email = get_secret("PINTEREST_EMAIL")
    except Exception:
        pinterest_email = os.getenv("PINTEREST_EMAIL", "dry_run@meeeshop.com" if dry_run else "")

    try:
        pinterest_password = get_secret("PINTEREST_PASSWORD")
    except Exception:
        pinterest_password = os.getenv("PINTEREST_PASSWORD", "dry_run_pass" if dry_run else "")

    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    if not dry_run and not all([pinterest_email, pinterest_password, shopify_url, shopify_token]):
        raise ValueError("Missing required credentials in .env")

    target = int(os.getenv("PINS_TO_POST", str(PINS_PER_RUN)))

    tracker = DailyPinTracker()
    logger.info(f"[V2] Daily run starting — target: {target} pins | {tracker.summary()}")
    if not dry_run and not tracker.can_post(n=1):
        logger.info("[V2] Daily cap reached — skipping this run. Good job posting today!")
        return

    history = reset_daily_count()

    already_today = history["daily_count"]
    if already_today >= MAX_PINS_PER_DAY:
        logger.info(f"Daily cap already reached ({already_today}), skipping")
        return

    target = min(target, MAX_PINS_PER_DAY - already_today)

    pinterest = PinterestClient()
    shopify = ShopifyClient(shopify_url, shopify_token)

    try:
        boards = []
        if not dry_run:
            if not pinterest.login():
                raise RuntimeError("Pinterest login failed")
            boards = pinterest.fetch_boards()

        if not boards:
            from board_mapping import MEEESHOP_BOARDS

            boards = [{"name": b, "id": f"mock_{i}"} for i, b in enumerate(MEEESHOP_BOARDS)]

        logger.info(f"Loaded {len(boards)} boards")

        run_board_pool = build_run_board_pool(boards, history, target)
        save_history(history)

        pool = fetch_all_eligible_products(shopify, history, min_stock=1)
        if not pool:
            logger.warning("No eligible products — skipping execution to avoid spam.")
            return

        posted = 0
        used_boards: set = set()
        used_product_indices: set = set()

        last_style = history.get("last_image_style")
        last_template = history.get("last_template_index")
        last_category = history.get("last_product_category")

        while posted < target and len(used_product_indices) < len(pool):
            selected_idx = select_next_product_lru(pool, used_product_indices, history)

            if selected_idx is None:
                break

            used_product_indices.add(selected_idx)
            product = pool[selected_idx]
            cat_used = get_product_main_category(product.get("title", ""), product.get("product_type", ""), product.get("tags", ""))

            formatted = format_product_for_pinterest(product, store_base_url)
            board_info = pick_board(posted, boards, used_boards, formatted, run_board_pool, history)
            if not board_info:
                logger.warning("No board available, skipping product")
                continue

            board = board_info["name"]
            board_id = board_info["id"]
            logger.info(f"Pin {posted + 1}/{target} → {board} (Category: {cat_used})")

            content = generate_content_package(formatted, board)

            if dry_run:
                from image_overlay import get_next_style_and_template
                dry_style, dry_tmpl = get_next_style_and_template(last_style, last_template, board, formatted["title"])
                logger.info(f"  [DRY RUN] Would design pin image for product {product['id']} (Category: {cat_used}, Style: {dry_style}, Template: {dry_tmpl})")
                logger.info(f"  [DRY RUN] Would generate AI title/description for board '{board}'")
                logger.info(f"  [DRY RUN] Would create pin on board '{board}' (ID: {board_id}) with URL '{formatted['url']}'")
                used_boards.add(board)
                last_style, last_template, last_category = dry_style, dry_tmpl, cat_used
                if "category_last_used" not in history:
                    history["category_last_used"] = {}
                history["category_last_used"][cat_used] = datetime.now().isoformat()
                posted += 1
                continue

            success, style_used, template_used = post_pin(
                pinterest, formatted, board_id, board, content, last_style, last_template
            )
            if not success:
                logger.warning(f"Post failed for '{formatted['title']}', trying next")
                continue

            last_style = style_used
            last_template = template_used
            last_category = cat_used

            if "category_last_used" not in history:
                history["category_last_used"] = {}
            history["category_last_used"][cat_used] = datetime.now().isoformat()

            history["posts"].append({
                "product_id": product["id"],
                "title": formatted["title"],
                "board": board,
                "timestamp": datetime.now().isoformat(),
                "style": style_used,
                "template": template_used,
                "category": cat_used,
            })
            history["board_last_used"][board] = datetime.now().isoformat()
            history["last_image_style"] = style_used
            history["last_template_index"] = template_used
            history["last_product_category"] = cat_used
            history["daily_count"] += 1
            history["last_post_time"] = datetime.now().isoformat()
            save_history(history)

            used_boards.add(board)
            posted += 1
            if not dry_run:
                tracker.record(n=1, source="daily_v2")

            if posted < target:
                delay = random.randint(5, 10)
                logger.info(f"Waiting {delay}s...")
                time.sleep(delay)

        logger.info(f"[V2] ✓ Done: {posted}/{target} pins posted. {tracker.summary()}")

    except Exception as e:
        logger.error(f"Daily posting error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    run_daily_posting()
