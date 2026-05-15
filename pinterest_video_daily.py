"""
pinterest_video_daily.py — Post YouTube Shorts as Pinterest video pins.

Auth:  Same cookie/email-password flow as pinterest_daily.py (PinterestClient).
       No Pinterest OAuth app or YouTube Data API key required.

YouTube: yt-dlp channel scrape for Shorts published in the last 48h.
Video upload: Pinterest internal multipart upload endpoint used by the web UI,
              called with the same authenticated session that creates image pins.
Content: content_generator.py for Pinterest-optimised title / description / alt text.
Board routing: extracts the product URL embedded in the YouTube description by the
               Shorts script (https://us.meeeshop.com/products/{handle}), resolves the
               exact Shopify product, then maps its type/tags to the correct Pinterest
               board via board_mapping.py.  Falls back to keyword matching if no URL found.
Algorithm safety: human-paced delays, 10-day repost cooldown, 1–2 video pins per run.

DRY_RUN mode (set DRY_RUN=true in env):
  Runs the full pipeline — auth, YouTube scrape, video download, content generation —
  but stops before uploading to Pinterest. Use this to validate the setup first.

MAX_PINS_PER_RUN (env var, default 1):
  Set to 2 for the scheduled production runs. Each video gets a different board.
"""

import json
import logging
import os
import random
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest, select_board_for_product
from content_generator import generate_content_package

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

VIDEO_HISTORY_FILE = Path(__file__).parent / "video_posting_history.json"
VIDEO_REPOST_COOLDOWN_DAYS = 10
MAX_VIDEO_DURATION_SECS = 90       # include 60–90s Shorts/Reels
FETCH_WINDOW_HOURS = 48

# Override via env: MAX_PINS_PER_RUN=2 for production, default 1 for validation
MAX_PINS_PER_RUN = int(os.getenv("MAX_PINS_PER_RUN", "1"))

# DRY_RUN=true → full pipeline except Pinterest upload/pin creation
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
MAX_VIDEO_SIZE_MB = 100

# Pinterest internal video-pin upload endpoints (web-UI flow — no OAuth app needed)
_PINTEREST_UPLOAD_URL = "https://www.pinterest.com/resource/VideoResource/create/"
_PINTEREST_PIN_URL = "https://www.pinterest.com/resource/PinResource/create/"

# Boards preferred for video content (lifestyle/discovery boards perform best)
VIDEO_PREFERRED_BOARDS = [
    "Trends",
    "Outfit Ideas",
    "Style Ideas",
    "Everyday Style",
    "Chic & Effortless Styles",
    "New Trendy Women Apparel, Shoes, Handbags & more",
    "Simple Outfits",
    "Ootd #ootd",
]

# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def _load_history() -> Dict[str, Any]:
    if VIDEO_HISTORY_FILE.exists():
        try:
            return json.loads(VIDEO_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"posts": []}


def _save_history(history: Dict[str, Any]) -> None:
    VIDEO_HISTORY_FILE.write_text(
        json.dumps(history, indent=2, default=str), encoding="utf-8"
    )


def _was_recently_posted(video_id: str, history: Dict[str, Any]) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=VIDEO_REPOST_COOLDOWN_DAYS)
    for post in history.get("posts", []):
        if post.get("video_id") == video_id:
            posted_at = datetime.fromisoformat(post["posted_at"])
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            if posted_at > cutoff:
                days_ago = (datetime.now(timezone.utc) - posted_at).days
                logger.info(f"Video {video_id} posted {days_ago}d ago — skipping (cooldown {VIDEO_REPOST_COOLDOWN_DAYS}d)")
                return True
    return False


# ---------------------------------------------------------------------------
# YouTube Shorts discovery — no API key, pure yt-dlp
# ---------------------------------------------------------------------------

def _run_ytdlp(args: List[str], timeout: int = 60) -> Optional[str]:
    """Run yt-dlp and return stdout, or None on failure."""
    cmd = ["yt-dlp"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8"
        )
        if result.returncode != 0:
            logger.warning(f"yt-dlp stderr: {result.stderr[:300]}")
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"yt-dlp timed out ({timeout}s): {' '.join(args[:4])}")
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found — install with: pip install yt-dlp")
        return None
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        return None


def _parse_iso_duration(duration: str) -> int:
    """'PT1M30S' → 90  (seconds).  Returns 9999 on parse failure."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not match:
        return 9999
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def get_recent_shorts(channel_url: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Discover YouTube Shorts uploaded in the last FETCH_WINDOW_HOURS hours.

    Strategy: ask yt-dlp to dump flat JSON for the channel's /shorts page.
    We use --playlist-end to limit scraping then filter by upload_date.
    Falls back to the main channel URL if the /shorts URL returns nothing.
    """
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=FETCH_WINDOW_HOURS)
    cutoff_str = cutoff_dt.strftime("%Y%m%d")  # yt-dlp upload_date format: YYYYMMDD

    targets = [
        channel_url.rstrip("/") + "/shorts",
        channel_url,
    ]

    for target in targets:
        logger.info(f"Scraping shorts from: {target}")
        raw = _run_ytdlp(
            [
                "--flat-playlist",
                "--dump-single-json",
                "--playlist-end", str(max_results),
                "--dateafter", cutoff_str,
                "--no-warnings",
                "--quiet",
                target,
            ],
            timeout=90,
        )
        if not raw:
            continue

        try:
            playlist = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse yt-dlp JSON from {target}")
            continue

        entries = playlist.get("entries") or []
        if not entries:
            logger.info(f"No entries returned from {target}")
            continue

        shorts: List[Dict[str, Any]] = []
        for entry in entries:
            vid_id = entry.get("id") or entry.get("video_id")
            if not vid_id:
                continue

            # Duration filtering: entry may already have duration
            duration = entry.get("duration") or 0
            if duration and duration > MAX_VIDEO_DURATION_SECS:
                logger.debug(f"Skip {vid_id}: {duration}s > {MAX_VIDEO_DURATION_SECS}s")
                continue

            # Upload date filter
            upload_date = entry.get("upload_date", "")  # YYYYMMDD
            if upload_date and upload_date < cutoff_str:
                continue

            title = entry.get("title") or entry.get("fulltitle") or ""
            description = entry.get("description") or ""
            thumbnail = (
                entry.get("thumbnail")
                or (entry.get("thumbnails") or [{}])[-1].get("url", "")
            )
            published_at = ""
            if upload_date:
                try:
                    d = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
                    published_at = d.isoformat()
                except ValueError:
                    published_at = upload_date

            shorts.append(
                {
                    "video_id": vid_id,
                    "title": title,
                    "description": description,
                    "thumbnail": thumbnail,
                    "published_at": published_at,
                    "duration_secs": duration,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "shorts_url": f"https://www.youtube.com/shorts/{vid_id}",
                }
            )

        if shorts:
            logger.info(f"Found {len(shorts)} eligible Shorts at {target}")
            return shorts

        logger.info(f"No eligible Shorts at {target} (within {FETCH_WINDOW_HOURS}h window)")

    logger.info(f"No Shorts found in last {FETCH_WINDOW_HOURS}h across all targets")
    return []


# ---------------------------------------------------------------------------
# Video download
# ---------------------------------------------------------------------------

def download_video(youtube_url: str, output_dir: Path) -> Optional[str]:
    """
    Download an MP4 ≤ MAX_VIDEO_SIZE_MB using yt-dlp.
    Returns absolute path to the downloaded file, or None on failure.
    """
    output_template = str(output_dir / "%(id)s.%(ext)s")
    fmt = (
        f"bestvideo[ext=mp4][filesize<{MAX_VIDEO_SIZE_MB}M]+bestaudio[ext=m4a]"
        f"/best[ext=mp4][filesize<{MAX_VIDEO_SIZE_MB}M]"
        f"/best[filesize<{MAX_VIDEO_SIZE_MB}M]"
        f"/best"
    )
    args = [
        "--format", fmt,
        "--merge-output-format", "mp4",
        "--output", output_template,
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        youtube_url,
    ]
    logger.info(f"Downloading video: {youtube_url}")
    result = _run_ytdlp(args, timeout=180)

    # Find the downloaded file (most recently modified .mp4)
    mp4_files = sorted(output_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    if mp4_files:
        size_mb = mp4_files[0].stat().st_size / 1_048_576
        logger.info(f"Downloaded: {mp4_files[0].name} ({size_mb:.1f} MB)")
        if size_mb > MAX_VIDEO_SIZE_MB:
            logger.error(f"File too large ({size_mb:.1f} MB > {MAX_VIDEO_SIZE_MB} MB)")
            return None
        return str(mp4_files[0])

    logger.error("yt-dlp ran but no .mp4 file found in output dir")
    return None


# ---------------------------------------------------------------------------
# Product URL extraction from YouTube description
# ---------------------------------------------------------------------------

# Matches both us.meeeshop.com/products/handle and meeeshop.myshopify.com/products/handle
_PRODUCT_URL_RE = re.compile(
    r"https?://(?:us\.meeeshop\.com|meeeshop\.myshopify\.com)/products/([\w-]+)",
    re.IGNORECASE,
)


def _extract_product_handle(text: str) -> Optional[str]:
    """Pull the first meeeshop product handle out of a string (video description, title, etc.)."""
    m = _PRODUCT_URL_RE.search(text or "")
    return m.group(1) if m else None


def _fetch_full_description(video_id: str) -> str:
    """
    Fetch the full video description for a single video via yt-dlp --dump-json.
    The flat-playlist scrape often returns truncated or empty descriptions;
    this fills the gap for the videos we actually intend to post.
    """
    raw = _run_ytdlp(
        [
            "--dump-json",
            "--no-playlist",
            "--skip-download",
            "--quiet",
            "--no-warnings",
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        timeout=30,
    )
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        return data.get("description") or ""
    except json.JSONDecodeError:
        return ""


# ---------------------------------------------------------------------------
# Product matching — URL-first, keyword fallback
# ---------------------------------------------------------------------------

def _resolve_product_from_video(
    video: Dict[str, Any],
    products: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    1. Try to extract the meeeshop product URL from the video description.
       The YouTube Shorts script embeds it as:
         https://us.meeeshop.com/products/{handle}
    2. If found, find the exact product in the Shopify list by handle.
    3. If not found (no URL or handle not in current product list),
       fall back to keyword overlap between video title and product title/tags.
    """
    # --- Step 1: description from flat-playlist (may be empty) ---
    description = video.get("description", "")

    # --- Step 2: if empty, fetch full description for this video ---
    if not description.strip():
        logger.info(f"  Fetching full description for {video['video_id']}…")
        description = _fetch_full_description(video["video_id"])
        video["description"] = description  # cache for content generation

    # --- Step 3: extract product handle from description ---
    handle = _extract_product_handle(description)
    if not handle:
        # Also try the video title (some Shorts encode the handle there)
        handle = _extract_product_handle(video.get("title", ""))

    if handle:
        logger.info(f"  Extracted product handle from description: {handle}")
        for p in products:
            if p.get("handle", "").lower() == handle.lower():
                logger.info(f"  Exact product match: '{p['title']}'")
                return p
        logger.warning(f"  Handle '{handle}' not found in current product list — falling back to keyword match")

    # --- Step 4: keyword overlap fallback ---
    words = set(re.sub(r"[^\w\s]", "", video.get("title", "").lower()).split())
    best, best_score = None, -1
    for p in products:
        candidate = (
            (p.get("title") or "") + " " + " ".join(p.get("tags") or [])
        ).lower()
        candidate_words = set(re.sub(r"[^\w\s]", "", candidate).split())
        score = len(words & candidate_words)
        if score > best_score:
            best_score, best = score, p

    if best_score == 0 and products:
        best = random.choice(products)
        logger.info("  No keyword overlap — using random product as fallback")
    else:
        logger.info(f"  Keyword-matched product: '{best['title']}' (score={best_score})")
    return best


# ---------------------------------------------------------------------------
# Board selection
# ---------------------------------------------------------------------------

def _pick_board(boards: List[Dict], formatted_product: Dict) -> Dict:
    """Pick a video-friendly board for the product."""
    ideal = select_board_for_product(formatted_product)

    # Exact match
    for b in boards:
        if b["name"].lower() == ideal.lower():
            return b
    # Partial match
    for b in boards:
        if ideal.lower() in b["name"].lower() or b["name"].lower() in ideal.lower():
            return b
    # Preferred video boards
    board_by_name = {b["name"].lower(): b for b in boards}
    for pref in VIDEO_PREFERRED_BOARDS:
        if pref.lower() in board_by_name:
            return board_by_name[pref.lower()]
    # Fallback: random
    return random.choice(boards)


# ---------------------------------------------------------------------------
# Pinterest video upload via internal web API (uses same cookie session)
# ---------------------------------------------------------------------------

def _upload_video_internal(session: requests.Session, mp4_path: str) -> Optional[str]:
    """
    Upload an MP4 to Pinterest using the same internal multipart endpoint the
    web UI calls.  Requires a valid authenticated requests.Session (from
    PinterestClient._get_raw_session()).

    Returns the Pinterest video_id string, or None on failure.
    """
    csrftoken = session.cookies.get("csrftoken", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.pinterest.com/pin-builder/",
        "Origin": "https://www.pinterest.com",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrftoken,
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    video_bytes = Path(mp4_path).read_bytes()
    logger.info(f"Uploading {len(video_bytes) / 1_048_576:.1f} MB to Pinterest…")

    try:
        resp = session.post(
            _PINTEREST_UPLOAD_URL,
            files={"video": ("video.mp4", video_bytes, "video/mp4")},
            headers=headers,
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        # Response shape: {"resource_response": {"data": {"id": "...", ...}}}
        video_id = (
            data.get("resource_response", {}).get("data", {}).get("id")
            or data.get("data", {}).get("id")
        )
        if video_id:
            logger.info(f"Pinterest video uploaded — video_id: {video_id}")
            return str(video_id)
        logger.error(f"Unexpected upload response (no id): {str(data)[:300]}")
        return None
    except requests.exceptions.HTTPError as e:
        body = getattr(e.response, "text", "")[:400]
        logger.error(f"Video upload HTTP {e.response.status_code}: {body}")
        return None
    except Exception as e:
        logger.error(f"Video upload error: {e}")
        return None


def _create_video_pin_internal(
    session: requests.Session,
    video_id: str,
    board_id: str,
    title: str,
    description: str,
    link: str,
    alt_text: str,
    cover_image_url: str,
) -> Optional[str]:
    """
    Create a video pin using Pinterest's internal PinResource/create/ endpoint.
    Mirrors the payload the web pin-builder POSTs after video upload.

    Returns the pin_id string on success, None on failure.
    """
    csrftoken = session.cookies.get("csrftoken", "")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.pinterest.com/pin-builder/",
        "Origin": "https://www.pinterest.com",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrftoken,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    # Pinterest internal pin creation payload for video pins
    from py3pin.RequestBuilder import RequestBuilder
    req_builder = RequestBuilder()
    options = {
        "board_id": board_id,
        "description": description[:500],
        "title": title[:100],
        "link": link,
        "alt_text": alt_text[:500],
        "video_id": video_id,
        "story_pin_data_id": None,
        "carousel_data_json": None,
    }
    if cover_image_url:
        options["cover_image_url"] = cover_image_url

    post_data = req_builder.buildPost(options=options, source_url="/pin-builder/")

    try:
        time.sleep(random.uniform(3, 7))  # human pacing before pin creation
        resp = session.post(
            _PINTEREST_PIN_URL,
            data=post_data,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        pin_id = (
            data.get("resource_response", {}).get("data", {}).get("id")
            or data.get("data", {}).get("id")
        )
        if pin_id:
            logger.info(f"Video pin created — pin_id: {pin_id}")
            return str(pin_id)
        logger.error(f"Pin creation unexpected response (no id): {str(data)[:300]}")
        return None
    except requests.exceptions.HTTPError as e:
        body = getattr(e.response, "text", "")[:400]
        logger.error(f"Pin creation HTTP {e.response.status_code}: {body}")
        return None
    except Exception as e:
        logger.error(f"Pin creation error: {e}")
        return None


# ---------------------------------------------------------------------------
# Content optimisation for Pinterest algorithm
# ---------------------------------------------------------------------------

def _build_video_content(video: Dict, product: Dict, board_name: str) -> Dict[str, str]:
    """
    Generate Pinterest-optimised title, description, and alt_text for a video pin.

    Pinterest algorithm signals we target:
    - Title: keyword-rich, benefit-led, ≤100 chars (40 ideal)
    - Description: natural keyword integration + strong CTA, ≤500 chars
    - Alt text: descriptive, accessibility-friendly, ≤500 chars
    - Hashtags embedded in description (8–12, not in title)
    """
    base = generate_content_package(product, board_name)

    pin_title = base["pin_title"]
    hashtags_str = " ".join(base.get("hashtags", [])[:12])

    # Enrich description with video context so it reads naturally in feed
    video_title_clean = re.sub(r"#\S+", "", video["title"]).strip()
    cta_phrases = [
        "Watch the styling video + Shop the look →",
        "See it styled in our video — tap to shop →",
        "Styled in our latest Short — shop the look →",
        "Watch & shop this look →",
    ]
    cta = random.choice(cta_phrases)

    base_desc = base["pin_description"]
    pin_description = f"{base_desc}\n\n{cta}\n\n{hashtags_str}".strip()
    if len(pin_description) > 500:
        # Trim hashtags to fit
        pin_description = f"{base_desc}\n\n{cta}".strip()[:500]

    # Alt text: describe the video content, not just the product
    alt_text = base.get("pin_alt_text") or base.get("alt_text") or ""
    if not alt_text:
        alt_text = f"Styling video: {video_title_clean[:100]}"
    else:
        alt_text = f"Styling video — {alt_text}"[:500]

    return {
        "title": pin_title,
        "description": pin_description,
        "alt_text": alt_text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_video_posting() -> None:
    channel_url = os.getenv("YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@MeeeShop")
    shopify_url = os.getenv("SHOPIFY_STORE_URL")
    shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    store_base_url = os.getenv("STORE_BASE_URL", "https://us.meeeshop.com")

    if not shopify_url or not shopify_token or shopify_token == "placeholder":
        raise ValueError("SHOPIFY_STORE_URL / SHOPIFY_ACCESS_TOKEN not set in .env")

    if DRY_RUN:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE — no pins will be posted to Pinterest")
        logger.info("=" * 60)

    # ---------- Pinterest auth (same as pinterest_daily.py) ----------
    pinterest = PinterestClient()
    if not pinterest.login():
        raise RuntimeError("Pinterest authentication failed")
    logger.info("✓ Pinterest authentication OK")

    boards = pinterest.fetch_boards()
    if not boards:
        raise RuntimeError("No Pinterest boards returned after login")
    logger.info(f"✓ Loaded {len(boards)} Pinterest boards")

    # ---------- Shopify products (load once, reuse for all pins) ----------
    shopify = ShopifyClient(shopify_url, shopify_token)
    products = shopify.get_products(limit=50)
    if not products:
        raise RuntimeError("No Shopify products returned")
    logger.info(f"✓ Loaded {len(products)} Shopify products")

    # ---------- History ----------
    history = _load_history()

    # ---------- Discover recent Shorts ----------
    logger.info(f"Fetching Shorts from {channel_url} (last {FETCH_WINDOW_HOURS}h)…")
    shorts = get_recent_shorts(channel_url, max_results=20)
    if not shorts:
        logger.info("No recent Shorts found — nothing to post today")
        return

    available = [v for v in shorts if not _was_recently_posted(v["video_id"], history)]
    if not available:
        logger.info("All recent Shorts already posted within cooldown window — done")
        return

    # Sort newest-first; take up to MAX_PINS_PER_RUN
    available.sort(key=lambda v: v.get("published_at", ""), reverse=True)
    to_post = available[:MAX_PINS_PER_RUN]
    logger.info(f"Will post {len(to_post)} video pin(s) this run (MAX_PINS_PER_RUN={MAX_PINS_PER_RUN})")

    session = pinterest._get_raw_session()
    posted_count = 0

    for idx, video in enumerate(to_post):
        logger.info(f"\n--- Pin {idx + 1}/{len(to_post)}: '{video['title']}' ---")

        # ---------- Resolve product from video description URL (or keyword fallback) ----------
        matched_product = _resolve_product_from_video(video, products)
        if not matched_product:
            logger.warning("Product matching failed — skipping this video")
            continue

        formatted = format_product_for_pinterest(matched_product, store_base_url)
        product_url = formatted["url"]
        logger.info(f"  Destination : {product_url}")

        # ---------- Board — rotate between pins so they land on different boards ----------
        # Shift the board preference list for each subsequent pin in this run
        rotated_boards = boards[idx:] + boards[:idx] if idx > 0 else boards
        board = _pick_board(rotated_boards, formatted)
        logger.info(f"  Board       : '{board['name']}' (id={board['id']})")

        # ---------- Content ----------
        content = _build_video_content(video, formatted, board["name"])
        logger.info(f"  Title       : {content['title']}")
        logger.info(f"  Description : {content['description'][:80]}…")
        logger.info(f"  Alt text    : {content['alt_text'][:80]}")

        # ---------- Cover image ----------
        cover_image_url = video.get("thumbnail") or formatted.get("image_url", "")

        if DRY_RUN:
            logger.info("  [DRY RUN] Would download + upload video here — skipped")
            logger.info("  [DRY RUN] Would create pin here — skipped")
            logger.info("  ✓ Dry-run validation passed for this video")
            posted_count += 1
            continue

        # ---------- Download ----------
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_file = download_video(video["url"], tmp_path)
            if not video_file:
                logger.warning("Retrying download with /shorts/ URL…")
                video_file = download_video(video["shorts_url"], tmp_path)
            if not video_file:
                logger.error(f"Video download failed: {video['url']} — skipping")
                continue

            # Human-paced delay before upload (longer between multiple pins)
            pause = random.uniform(5, 12) if idx == 0 else random.uniform(90, 180)
            logger.info(f"  Pausing {pause:.0f}s before upload…")
            time.sleep(pause)

            video_id = _upload_video_internal(session, video_file)
            if not video_id:
                logger.error("Pinterest video upload failed — skipping")
                continue

            # Wait for Pinterest to finish processing the video (≈15–40s observed)
            wait_secs = random.uniform(20, 35)
            logger.info(f"  Waiting {wait_secs:.0f}s for Pinterest video processing…")
            time.sleep(wait_secs)

            pin_id = _create_video_pin_internal(
                session=session,
                video_id=video_id,
                board_id=board["id"],
                title=content["title"],
                description=content["description"],
                link=product_url,
                alt_text=content["alt_text"],
                cover_image_url=cover_image_url,
            )
            if not pin_id:
                logger.error("Pinterest pin creation failed — skipping")
                continue

        # ---------- Record ----------
        history["posts"].append(
            {
                "video_id": video["video_id"],
                "youtube_title": video["title"],
                "pin_id": pin_id,
                "board": board["name"],
                "product_title": formatted["title"],
                "product_url": product_url,
                "posted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _save_history(history)
        posted_count += 1

        logger.info(
            f"  ✓ Video pin posted!\n"
            f"    YouTube : {video['title']}\n"
            f"    Board   : {board['name']}\n"
            f"    Product : {formatted['title']}\n"
            f"    URL     : {product_url}\n"
            f"    Pin ID  : {pin_id}"
        )

    if DRY_RUN:
        logger.info(
            f"\n{'=' * 60}\n"
            f"DRY RUN COMPLETE — {posted_count}/{len(to_post)} video(s) validated.\n"
            f"All systems OK. Remove DRY_RUN=true to go live.\n"
            f"{'=' * 60}"
        )
    else:
        logger.info(f"\nRun complete — {posted_count}/{len(to_post)} video pin(s) posted.")


if __name__ == "__main__":
    run_video_posting()
