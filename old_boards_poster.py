#!/usr/bin/env python3
"""
old_boards_poster.py — Targeted pin posting script for 1-year-old Pinterest boards.

Revives organic reach and drives traffic to MeeeShop's established 1-year-old Pinterest boards
by matching active Shopify products to relevant old board titles.
"""

import os
import sys
import json
import random
import time
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).parent))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest
from content_generator_v2 import generate_content_package
from board_mapping import (
    OLD_BOARDS_1Y,
    MEEESHOP_BOARDS,
    get_candidate_boards_for_product,
    select_best_lru_board,
    match_live_board,
)
from image_overlay import add_text_overlay, get_next_style_and_template
from daily_pin_tracker import DailyPinTracker
from video_picker import EnvLoader

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "posting_history_v2.json"
DEFAULT_OLD_PINS_PER_RUN = 4


def load_history() -> Dict[str, Any]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "posts": [],
        "board_last_used": {},
        "daily_count": 0,
        "last_post_time": None,
        "board_rotation_cursor": 0,
    }


def save_history(history: Dict[str, Any]):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def download_image(url: str, save_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        logger.error(f"Failed to download image {url}: {e}")
        return False


def post_pin_to_old_board(
    client: PinterestClient,
    product_data: Dict[str, Any],
    board_id: str,
    board_name: str,
    content: Dict[str, Any],
    last_style: Optional[str] = None,
    last_template: Optional[int] = None,
) -> Tuple[bool, Optional[str], Optional[int]]:

    image_file = Path("/tmp") / f"old_pin_{product_data['product_id']}.jpg"
    if not download_image(product_data["image_url"], image_file):
        logger.error(f"Failed image download for: {content['pin_title']}")
        return False, None, None

    additional_image_files = []
    overlay_image = None

    style_used, template_used = get_next_style_and_template(
        last_style=last_style,
        last_template=last_template,
        board_name=board_name,
        title=content["pin_title"],
    )

    try:
        all_image_urls = product_data.get("all_image_urls", [])
        extra_urls = [u for u in all_image_urls if u != product_data["image_url"]][:3]
        for idx, url in enumerate(extra_urls):
            temp_img = Path("/tmp") / f"old_pin_extra_{product_data['product_id']}_{idx}.jpg"
            if download_image(url, temp_img):
                additional_image_files.append(temp_img)

        overlay_file = Path("/tmp") / f"old_pin_overlay_{product_data['product_id']}.jpg"
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
            overlay_image = str(image_file)

        logger.info(f"Creating pin on 1y board '{board_name}' (Style: {style_used}): {content['pin_title']}")

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
            logger.info(f"✓ Posted to 1y board '{board_name}': {content['pin_title']} (ID: {pin_id})")
            return True, style_used, template_used
        else:
            logger.error(f"✗ Failed posting to '{board_name}': {content['pin_title']}")
            return False, None, None

    except Exception as e:
        logger.error(f"Exception posting to 1y board: {e}", exc_info=True)
        return False, None, None
    finally:
        image_file.unlink(missing_ok=True)
        if overlay_image and Path(overlay_image).exists() and overlay_image != str(image_file):
            Path(overlay_image).unlink(missing_ok=True)
        for f in additional_image_files:
            f.unlink(missing_ok=True)


def fetch_eligible_products(shopify: ShopifyClient, history: Dict[str, Any]) -> List[Dict[str, Any]]:
    products = shopify.get_all_products(status="active")
    logger.info(f"Fetched {len(products)} total products from Shopify")

    three_days_ago = datetime.now() - timedelta(days=3)
    recent_ids = set()
    for p in history.get("posts", []):
        ts_str = p.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                if ts > three_days_ago:
                    recent_ids.add(str(p.get("product_id")))
            except Exception:
                pass

    eligible = [
        p for p in products
        if str(p.get("id")) not in recent_ids
        and any(v.get("inventory_quantity", 0) >= 1 for v in p.get("variants", []))
    ]
    logger.info(f"Eligible products for 1y board posting: {len(eligible)}")
    random.shuffle(eligible)
    return eligible


def run_old_boards_posting(pins_count: int = DEFAULT_OLD_PINS_PER_RUN, dry_run: bool = False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    EnvLoader.load_youtube_env()
    if dry_run:
        logger.info("=" * 60)
        logger.info("[DRY RUN MODE ENABLED] No live pins will be created on Pinterest.")
        logger.info("=" * 60)

    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    history = load_history()
    tracker = DailyPinTracker()
    logger.info(f"Starting 1y Boards Poster — Target: {pins_count} pins | {tracker.summary()}")

    pinterest = PinterestClient()
    shopify = ShopifyClient(shopify_url, shopify_token)

    try:
        boards = []
        if not dry_run:
            if not pinterest.login():
                raise RuntimeError("Pinterest login failed")
            boards = pinterest.fetch_boards()

        if not boards:
            boards = [{"name": b, "id": f"mock_{i}"} for i, b in enumerate(MEEESHOP_BOARDS)]

        logger.info(f"Loaded {len(boards)} boards from Pinterest")

        # Filter boards matching OLD_BOARDS_1Y
        old_live_boards = []
        for old_title in OLD_BOARDS_1Y:
            matched = match_live_board(old_title, boards)
            if matched and matched not in old_live_boards:
                old_live_boards.append(matched)

        if not old_live_boards:
            logger.warning("No 1-year-old boards matched in live account — using all live boards as fallback")
            old_live_boards = boards

        logger.info(f"Matched {len(old_live_boards)} active 1-year-old boards on Pinterest account:")
        for b in old_live_boards:
            logger.info(f"  - {b.get('name')}")

        products = fetch_eligible_products(shopify, history)
        if not products:
            logger.warning("No eligible products available for posting.")
            return

        posted = 0
        used_boards: set = set()
        used_product_indices: set = set()

        last_style = history.get("last_image_style")
        last_template = history.get("last_template_index")

        while posted < pins_count and len(used_product_indices) < len(products):
            # Pick next candidate product
            selected_idx = next(i for i in range(len(products)) if i not in used_product_indices)
            used_product_indices.add(selected_idx)
            product = products[selected_idx]

            formatted = format_product_for_pinterest(product, store_base_url)

            # Select best 1y LRU board matching product category
            target_board_dict = select_best_lru_board(
                product_title=formatted["title"],
                product_type=formatted.get("product_type", ""),
                live_boards=old_live_boards,
                board_last_used=history.get("board_last_used", {}),
                used_boards_in_run=used_boards,
                prioritize_old_boards=True,
            )

            board_name = target_board_dict.get("name")
            board_id = target_board_dict.get("id")

            logger.info(f"\n[Pin {posted+1}/{pins_count}] Product: '{formatted['title']}' → 1y Board: '{board_name}'")
            content = generate_content_package(formatted, board_name)

            if dry_run:
                dry_style, dry_tmpl = get_next_style_and_template(last_style, last_template, board_name, formatted["title"])
                logger.info(f"  [DRY RUN] Would post pin for '{formatted['title']}' to 1y board '{board_name}'")
                logger.info(f"  [DRY RUN] Pin Title: {content['pin_title']}")
                logger.info(f"  [DRY RUN] Pin Description: {content['pin_description'][:100]}...")
                used_boards.add(board_name)
                last_style, last_template = dry_style, dry_tmpl
                posted += 1
                continue

            success, style_used, template_used = post_pin_to_old_board(
                pinterest, formatted, board_id, board_name, content, last_style, last_template
            )

            if not success:
                logger.warning(f"Post failed for '{formatted['title']}', continuing...")
                continue

            last_style = style_used
            last_template = template_used

            history["posts"].append({
                "product_id": product["id"],
                "title": formatted["title"],
                "board": board_name,
                "timestamp": datetime.now().isoformat(),
                "style": style_used,
                "template": template_used,
                "source": "old_boards_poster",
            })
            history["board_last_used"][board_name] = datetime.now().isoformat()
            history["last_image_style"] = style_used
            history["last_template_index"] = template_used
            history["daily_count"] = history.get("daily_count", 0) + 1
            history["last_post_time"] = datetime.now().isoformat()
            save_history(history)

            used_boards.add(board_name)
            posted += 1
            tracker.record(n=1, source="old_boards_poster")

            if posted < pins_count:
                delay = random.randint(5, 10)
                logger.info(f"Waiting {delay}s...")
                time.sleep(delay)

        logger.info(f"\n✓ Completed: {posted}/{pins_count} pins posted to 1-year-old boards.")

    except Exception as e:
        logger.error(f"1y board posting failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post relevant products to 1-year-old Pinterest boards")
    parser.add_argument("--pins-count", type=int, default=DEFAULT_OLD_PINS_PER_RUN, help="Number of pins to post")
    parser.add_argument("--dry-run", action="store_true", help="Simulate posting without creating pins")
    args = parser.parse_args()

    run_old_boards_posting(pins_count=args.pins_count, dry_run=args.dry_run)
