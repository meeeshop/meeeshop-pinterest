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
from board_mapping import select_best_lru_board, MEEESHOP_BOARDS

logging.basicConfig(
    level=logging.INFO,
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
        # ── CAROUSEL PIN: download multiple images, apply per-slide overlays ─────
        if pin_type == "carousel":
            all_urls = product_data.get("all_image_urls", [])
            if len(all_urls) < 2:
                logger.warning("Not enough product images for carousel, falling back to product pin")
                pin_type = "product"
            else:
                slide_images = []
                for slide_idx, img_url in enumerate(all_urls[:4]):
                    slide_raw = temp_dir / f"stealth_cslide_{product_data['product_id']}_{slide_idx}.jpg"
                    slide_overlay = temp_dir / f"stealth_cslide_ovl_{product_data['product_id']}_{slide_idx}.jpg"
                    if not download_image(img_url, slide_raw):
                        continue
                    # Slide 1: full overlay; subsequent slides: minimal overlay
                    _, tpl = get_next_style_and_template(
                        last_style=style_used,
                        last_template=template_used if slide_idx == 0 else (template_used + slide_idx) % 17,
                        board_name=board_name,
                        title=content["pin_title"],
                    )
                    slide_out = add_text_overlay(
                        str(slide_raw),
                        title=content["pin_title"] if slide_idx == 0 else "",
                        cta="Shop Now" if slide_idx == 0 else "",
                        price=product_data.get("price") if slide_idx == 0 else None,
                        output_path=str(slide_overlay),
                        template_index=tpl if slide_idx == 0 else 0,
                        board_name=board_name,
                        image_style="card" if slide_idx > 0 else style_used,
                    ) or str(slide_raw)
                    slide_images.append(slide_out)
                    slide_raw.unlink(missing_ok=True)

                if len(slide_images) >= 2:
                    logger.info(f"🎠 Posting CAROUSEL pin with {len(slide_images)} slides: {content['pin_title'][:60]}")
                    success, res_msg = poster.create_carousel_pin(
                        image_paths=slide_images,
                        title=content["pin_title"],
                        description=content["pin_description"],
                        board_name=board_name,
                        link_url=product_data["url"],
                        dry_run=dry_run,
                    )
                    for sp in slide_images:
                        Path(sp).unlink(missing_ok=True)
                    return success, style_used, template_used
                else:
                    logger.warning("Not enough slide images prepared, falling back to product pin")
                    pin_type = "product"
        # ── VIDEO PIN: generate mp4 slideshow from product images ──────────────
        if pin_type == "video":
            video_file = temp_dir / f"stealth_video_{product_data['product_id']}.mp4"
            all_urls = product_data.get("all_image_urls", [])
            # Download up to 3 product images for the slideshow
            slide_paths = []
            for idx, img_url in enumerate(all_urls[:3]):
                slide_path = temp_dir / f"stealth_slide_{product_data['product_id']}_{idx}.jpg"
                if download_image(img_url, slide_path):
                    slide_paths.append(str(slide_path))
            if len(slide_paths) < 2:
                # Fallback to single image repeated
                slide_paths = [str(image_file)] * 2

            video_ok = _generate_slideshow_video(slide_paths, str(video_file), duration_per_slide=3)
            if video_ok and video_file.exists():
                logger.info(f"🎥 Created slideshow video: {video_file} ({len(slide_paths)} slides)")
                success, res_msg = poster.create_pin(
                    image_path=str(video_file),
                    title=content["pin_title"],
                    description=content["pin_description"],
                    board_name=board_name,
                    link_url=product_data["url"],
                    alt_text=content.get("pin_alt_text"),
                    cover_image_path=str(image_file),   # ← cover thumbnail for video
                    dry_run=dry_run,
                )
                video_file.unlink(missing_ok=True)
                for sp in slide_paths:
                    Path(sp).unlink(missing_ok=True)
                return success, style_used, template_used
            else:
                logger.warning("Video generation failed, falling back to image pin")
                pin_type = "product"  # graceful fallback

        # ── IMAGE / BLOG PIN ────────────────────────────────────────────────────
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


def _generate_slideshow_video(
    image_paths: List[str],
    output_path: str,
    duration_per_slide: int = 3,
) -> bool:
    """
    Generate a slideshow MP4 from a list of image paths using ffmpeg.
    Each slide is shown for `duration_per_slide` seconds with a simple crossfade.
    Returns True on success.
    """
    import subprocess
    import shutil

    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg not found on PATH — cannot generate video pin")
        return False

    try:
        # Build an ffmpeg concat input: each image shown for N seconds
        concat_lines = []
        for path in image_paths:
            concat_lines.append(f"file '{path}'")
            concat_lines.append(f"duration {duration_per_slide}")
        # ffmpeg concat demuxer needs a last file line without duration
        concat_lines.append(f"file '{image_paths[-1]}'")

        concat_file = output_path + ".txt"
        with open(concat_file, "w") as f:
            f.write("\n".join(concat_lines))

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-vf", "scale=1000:1500:force_original_aspect_ratio=decrease,pad=1000:1500:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-r", "25",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        Path(concat_file).unlink(missing_ok=True)
        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr.decode()[-500:]}")
            return False
        return True
    except Exception as e:
        logger.error(f"Slideshow video generation error: {e}")
        return False


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

    # Exclude products posted recently (10-day cross-file check)
    ten_days_ago = datetime.now() - timedelta(days=10)
    recent_ids = set()
    for p in history.get("posts", []):
        ts_str = p.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is not None: ts = ts.replace(tzinfo=None)
                if ts > ten_days_ago:
                    recent_ids.add(str(p.get("product_id")))
            except Exception: pass

    other_histories = [
        ("refresh_history_v2.json", "refreshes", "timestamp"),
        ("video_posting_history.json", "posts", "posted_at"),
        ("blog_posting_history.json", "posts", "timestamp"),
        ("posting_history_v2.json", "posts", "timestamp"),
    ]
    for filename, list_key, time_key in other_histories:
        history_path = ROOT / filename
        if history_path.exists():
            try:
                hist_data = json.loads(history_path.read_text(encoding="utf-8"))
                for item in hist_data.get(list_key, []):
                    ts_str = item.get(time_key)
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts.tzinfo is not None: ts = ts.replace(tzinfo=None)
                        if ts > ten_days_ago:
                            item_id = item.get("product_id") or item.get("id")
                            if item_id: recent_ids.add(str(item_id))
            except Exception: pass

    eligible = [p for p in products if str(p.get("id")) not in recent_ids]
    if not eligible:
        logger.warning("All products posted in last 10 days! Falling back to 100% pool.")
        eligible = products

    random.shuffle(eligible)

    # Poster instance
    poster = StealthPinterestPoster(headless=True)

    posted_count = 0
    consecutive_failures = 0
    used_boards_in_run = set()

    store_base_url = safe_get_secret("STORE_BASE_URL") or safe_get_secret("SHOPIFY_STORE_URL")
    if not store_base_url:
        logger.error("❌ Missing STORE_BASE_URL / SHOPIFY_STORE_URL in secrets vault")
        return

    last_style = history.get("last_image_style")
    last_template = history.get("last_template_index")

    for raw_product in eligible:
        if posted_count >= limit or (history["daily_count"] + posted_count) >= MAX_PINS_PER_DAY:
            break

        formatted = format_product_for_pinterest(raw_product, store_base_url)
        if not formatted.get("image_url"):
            continue

        # Match board using MEEESHOP_BOARDS
        live_boards = [{"id": b, "name": b} for b in MEEESHOP_BOARDS]

        board = select_best_lru_board(
            product_title=formatted["title"],
            product_type=formatted["product_type"],
            live_boards=live_boards,
            board_last_used=history.get("board_last_used", {}),
            used_boards_in_run=used_boards_in_run,
        )

        board_name = board["name"] if board else "Trendy & Timeless Fashion"
        used_boards_in_run.add(board_name)

        # Content Mix: forced_type or 60% Product, 15% Video, 15% Carousel, 10% Blog
        if forced_type in ["product", "video", "blog", "carousel"]:
            pin_type = forced_type
        else:
            rand_val = random.random()
            if rand_val < 0.60:
                pin_type = "product"
            elif rand_val < 0.75:
                pin_type = "video"
            elif rand_val < 0.90:
                pin_type = "carousel"
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
            last_style=last_style,
            last_template=last_template,
            dry_run=dry_run,
        )

        if success:
            consecutive_failures = 0
            last_style = style_used
            last_template = template_used
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
        else:
            consecutive_failures += 1
            logger.warning(f"Stealth posting failed. Consecutive failures: {consecutive_failures}/1")
            if consecutive_failures >= 1:
                logger.error("Pin failed! Aborting run immediately as requested to prevent wasted minutes.")
                sys.exit(1)

    logger.info(f"🎯 Stealth daily run finished. Posted {posted_count} pins.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    forced_type = None
    for arg in sys.argv:
        if arg.startswith("--type="):
            forced_type = arg.split("=", 1)[1]
    run_daily_stealth_posting(dry_run=dry_run, forced_type=forced_type)
