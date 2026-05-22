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

import io
import os
import sys
import json
import logging
import random
import time
import hashlib
import zipfile
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


def fetch_posting_history_from_github() -> Optional[Dict[str, Any]]:
    """
    PRIMARY source: merge posting_history.json from ALL successful daily posting
    runs in the last 7 days via GitHub Actions API.

    Each run saves only its own 4 pins — we need to merge across runs to get
    the full week's worth of posts for the 48h–7day refresh window.

    Requires GITHUB_TOKEN and GITHUB_REPOSITORY env vars (auto-set in Actions).
    Returns merged history dict, or None if unavailable.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")

    if not token or not repo:
        logger.warning("GITHUB_TOKEN or GITHUB_REPOSITORY not set — cannot fetch artifact")
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base_api = f"https://api.github.com/repos/{repo}"
    seven_days_ago = datetime.now() - timedelta(days=7)

    try:
        # Fetch up to 50 recent runs — enough to cover 4 runs/day × 7 days = 28 runs
        resp = requests.get(
            f"{base_api}/actions/workflows/daily-pinterest-posting.yml/runs",
            headers=headers,
            params={"status": "success", "per_page": 50},
            timeout=15,
        )
        resp.raise_for_status()
        runs = resp.json().get("workflow_runs", [])

        if not runs:
            logger.warning("No successful daily posting runs found")
            return None

        # Filter to runs within the last 7 days
        recent_runs = []
        for run in runs:
            created = run.get("created_at", "")
            try:
                run_time = datetime.fromisoformat(created.replace("Z", ""))
                if run_time >= seven_days_ago:
                    recent_runs.append(run)
            except ValueError:
                continue

        logger.info(f"Found {len(recent_runs)} successful posting runs in the last 7 days")
        if not recent_runs:
            return None

        # Merge posts from all runs — deduplicate by product_id keeping earliest timestamp
        merged_posts: Dict[str, Dict] = {}  # product_id → post entry

        for run in recent_runs:
            run_id = run["id"]
            try:
                art_resp = requests.get(
                    f"{base_api}/actions/runs/{run_id}/artifacts",
                    headers=headers,
                    timeout=15,
                )
                art_resp.raise_for_status()
                artifacts = art_resp.json().get("artifacts", [])

                artifact = next(
                    (a for a in artifacts if a["name"].startswith("posting-history")),
                    None,
                )
                if not artifact:
                    continue

                dl_resp = requests.get(
                    artifact["archive_download_url"],
                    headers=headers,
                    timeout=30,
                    allow_redirects=True,
                )
                dl_resp.raise_for_status()

                with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
                    json_name = next(
                        (n for n in zf.namelist() if n.endswith("posting_history.json")),
                        None,
                    )
                    if not json_name:
                        continue
                    data = json.loads(zf.read(json_name).decode("utf-8"))

                for post in data.get("posts", []):
                    pid = str(post.get("product_id", ""))
                    if not pid or post.get("is_refresh"):
                        continue
                    # Keep earliest post per product (original pin time)
                    if pid not in merged_posts:
                        merged_posts[pid] = post
                    else:
                        existing_ts = merged_posts[pid].get("timestamp", "")
                        if post.get("timestamp", "") < existing_ts:
                            merged_posts[pid] = post

                logger.info(f"  Run #{run['run_number']}: merged, {len(merged_posts)} unique products so far")

            except Exception as run_err:
                logger.warning(f"  Run #{run['run_number']} skipped: {run_err}")
                continue

        if not merged_posts:
            logger.warning("No posts found across recent runs")
            return None

        logger.info(f"Merged {len(merged_posts)} unique original posts from last 7 days of runs")
        return {"posts": list(merged_posts.values()), "board_last_used": {}, "daily_count": 0, "last_post_time": None}

    except Exception as e:
        logger.warning(f"GitHub artifact fetch failed: {e}")
        return None


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

    history = load_history()
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

        # Build full product map from Shopify (by numeric ID and by handle)
        products = shopify.get_products(limit=250)
        product_map_by_id = {str(p["id"]): p for p in products}
        product_map_by_handle = {p["handle"]: p for p in products}

        # --- PRIMARY: fetch posting history from GitHub Actions artifact ---
        # This is the most reliable source — the daily workflow saves exactly what it posted.
        source_label = "local file"
        live_history = fetch_posting_history_from_github()
        if live_history:
            history = live_history
            source_label = "GitHub artifact"
        else:
            logger.info("GitHub artifact unavailable — using local posting_history.json")

        candidates = get_candidates(history, refresh_history)

        if not candidates:
            logger.info(f"No products due for refresh (source: {source_label})")
            return

        logger.info(f"{len(candidates)} products eligible for refresh (source: {source_label})")

        used_boards_today: set = set()
        refreshed = 0

        for post in candidates:
            if refreshed >= MAX_REFRESHES_PER_RUN:
                break

            refresh_num = post["_refresh_number"]
            original_board = post.get("board", "")

            # posting_history always uses numeric Shopify product ID
            product = product_map_by_id.get(str(post["product_id"]))

            if not product:
                logger.warning(f"Product '{post['product_id']}' not found in Shopify — skipping")
                continue

            pid = str(product["id"])
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
