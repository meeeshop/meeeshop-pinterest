"""
pinterest_daily_stealth.py — Stealth Daily Orchestrator

Uses Stealth Playwright UI automation (stealth_pinterest_poster.py) instead of py3pin scraping.
Maintains separate posting history (posting_history_stealth.json) so legacy posting_history_v2.json remains untouched as fallback.

Utilizes double-encryption secrets strategy (ENCRYPTION_KEY_PRIMARY & ENCRYPTION_KEY_FALLBACK).
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

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Double Encryption Secrets Initialization ─────────────────────────────────
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from shopify_products import ShopifyClient, format_product_for_pinterest
from content_generator_v2 import generate_content_package
from stealth_pinterest_poster import StealthPinterestPoster
from image_overlay import add_text_overlay, get_next_style_and_template
from board_mapping import select_best_lru_board

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)
logger = logging.getLogger(__name__)

HISTORY_FILE = ROOT / "posting_history_stealth.json"
MAX_PINS_PER_DAY = int(os.environ.get("PINTEREST_DAILY_CAP", "8"))
PINS_PER_RUN = int(os.environ.get("PINS_TO_POST", "2"))


def load_history() -> Dict[str, Any]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not parse history file: {e}")
    return {
        "posts": [],
        "board_last_used": {},
        "daily_count": 0,
        "last_post_time": None,
        "board_rotation_cursor": 0,
    }


def save_history(history: Dict[str, Any]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def reset_daily_count_if_new_day(history: Dict[str, Any]) -> Dict[str, Any]:
    last_post = history.get("last_post_time")
    if last_post:
        try:
            last_post_date = datetime.fromisoformat(last_post).date()
            if last_post_date != datetime.now().date():
                history["daily_count"] = 0
                save_history(history)
        except Exception:
            pass
    return history


def download_image(url: str, save_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        logger.error(f"Failed to download image {url}: {e}")
        return False


def post_single_pin_stealth(
    poster: StealthPinterestPoster,
    product_data: Dict[str, Any],
    board_name: str,
    content: Dict[str, Any],
    pin_type: str = "product",
    last_style: Optional[str] = None,
    last_template: Optional[int] = None,
    dry_run: bool = False,
) -> Tuple[bool, Optional[str], Optional[int]]:
    temp_dir = Path("/tmp") if os.name != "nt" else ROOT / "scratch"
    temp_dir.mkdir(parents=True, exist_ok=True)

    image_file = temp_dir / f"stealth_pin_{product_data['product_id']}.jpg"
    if not download_image(product_data["image_url"], image_file):
        return False, None, None

    style_used, template_used = get_next_style_and_template(
        last_style=last_style,
        last_template=last_template,
        board_name=board_name,
        title=content["pin_title"],
    )

    overlay_file = temp_dir / f"stealth_overlay_{product_data['product_id']}.jpg"
    try:
        overlay_image = add_text_overlay(
            str(image_file),
            title=content["pin_title"],
            cta="Shop Now" if pin_type != "blog" else "Read Post",
            price=product_data.get("price") if pin_type != "blog" else None,
            output_path=str(overlay_file),
            template_index=template_used,
            board_name=board_name,
            image_style=style_used,
        )
        if not overlay_image:
            overlay_image = str(image_file)

        logger.info(f"📌 Posting via Stealth Playwright UI (Type: {pin_type}, Style: {style_used}): {content['pin_title']}")

        success, res_msg = poster.create_pin(
            image_path=overlay_image,
            title=content["pin_title"],
            description=content["pin_description"],
            board_name=board_name,
            link_url=product_data["url"],
            alt_text=content.get("pin_alt_text"),
            dry_run=dry_run,
        )

        return success, style_used, template_used

    except Exception as e:
        logger.error(f"Exception during stealth posting: {e}", exc_info=True)
        return False, None, None
    finally:
        image_file.unlink(missing_ok=True)
        if overlay_file.exists():
            overlay_file.unlink(missing_ok=True)


def safe_get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        val = get_secret(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key, default)


def run_daily_stealth_posting(dry_run: bool = False, pins_count: Optional[int] = None, forced_type: Optional[str] = None):
    history = load_history()
    history = reset_daily_count_if_new_day(history)

    limit = pins_count or PINS_PER_RUN
    if history["daily_count"] >= MAX_PINS_PER_DAY:
        logger.warning(f"Daily cap reached ({history['daily_count']}/{MAX_PINS_PER_DAY}). Stopping.")
        return

    # Shopify client
    store_url = safe_get_secret("SHOPIFY_STORE_URL")
    access_token = safe_get_secret("SHOPIFY_ACCESS_TOKEN")

    if not store_url or not access_token:
        logger.error("Missing SHOPIFY_STORE_URL or SHOPIFY_ACCESS_TOKEN in secrets")
        return

    shopify = ShopifyClient(store_url, access_token)
    products = shopify.get_all_products(status="active")
    logger.info(f"Fetched {len(products)} total Shopify products")

    if not products:
        logger.warning("No products returned from Shopify")
        return

    # Exclude products posted recently
    recent_pids = {p.get("product_id") for p in history.get("posts", [])[-30:] if isinstance(p, dict)}
    eligible = [p for p in products if p.get("id") not in recent_pids]
    if not eligible:
        eligible = products

    random.shuffle(eligible)

    # Poster instance
    poster = StealthPinterestPoster(headless=True)

    posted_count = 0
    used_boards_in_run = set()

    store_base_url = safe_get_secret("STORE_BASE_URL") or safe_get_secret("SHOPIFY_STORE_URL")
    if not store_base_url:
        logger.error("❌ Missing STORE_BASE_URL / SHOPIFY_STORE_URL in secrets vault")
        return

    for raw_product in eligible:
        if posted_count >= limit or (history["daily_count"] + posted_count) >= MAX_PINS_PER_DAY:
            break

        formatted = format_product_for_pinterest(raw_product, store_base_url)
        if not formatted.get("image_url"):
            continue

        # Match board
        live_boards = [
            {"id": "b1", "name": "Dresses"},
            {"id": "b2", "name": "Trends"},
            {"id": "b3", "name": "Pants & Leggings"},
            {"id": "b4", "name": "Must-Have Fashion Picks"},
            {"id": "b5", "name": "Short fall dresses"},
            {"id": "b6", "name": "Feminine & Flowy Fits"},
            {"id": "b7", "name": "Trendy & Timeless Fashion"},
        ]

        board = select_best_lru_board(
            product_title=formatted["title"],
            product_type=formatted["product_type"],
            live_boards=live_boards,
            board_last_used=history.get("board_last_used", {}),
            used_boards_in_run=used_boards_in_run,
        )

        board_name = board["name"] if board else "Trendy & Timeless Fashion"
        used_boards_in_run.add(board_name)

        # Content Mix: forced_type or 70% Product, 20% Video, 10% Blog
        if forced_type in ["product", "video", "blog"]:
            pin_type = forced_type
        else:
            rand_val = random.random()
            if rand_val < 0.70:
                pin_type = "product"
            elif rand_val < 0.90:
                pin_type = "video"
            else:
                pin_type = "blog"

        # Generate V2 AI content
        content = generate_content_package(formatted, board_name)

        success, style_used, template_used = post_single_pin_stealth(
            poster=poster,
            product_data=formatted,
            board_name=board_name,
            content=content,
            pin_type=pin_type,
            last_style=history.get("last_image_style"),
            last_template=history.get("last_template_index"),
            dry_run=dry_run,
        )

        if success:
            posted_count += 1
            now_iso = datetime.now().isoformat()
            history["posts"].append({
                "product_id": formatted["product_id"],
                "title": content["pin_title"],
                "board": board_name,
                "timestamp": now_iso,
                "type": pin_type,
                "style": style_used,
                "template": template_used,
                "source": "stealth_playwright"
            })
            history["board_last_used"][board_name] = now_iso
            history["daily_count"] += 1
            history["last_post_time"] = now_iso
            history["last_image_style"] = style_used
            history["last_template_index"] = template_used

            save_history(history)
            logger.info(f"✓ Stealth posting successful ({posted_count}/{limit}) — Type: {pin_type}")
            time.sleep(random.uniform(5, 12))

    logger.info(f"🎯 Stealth daily run finished. Posted {posted_count} pins.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    forced_type = None
    for arg in sys.argv:
        if arg.startswith("--type="):
            forced_type = arg.split("=", 1)[1]
    run_daily_stealth_posting(dry_run=dry_run, forced_type=forced_type)
