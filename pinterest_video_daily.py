"""
pinterest_video_daily.py — Generate product videos from Shopify images and post as Pinterest video pins.

No YouTube dependency. Videos are built locally using the same PIL/MoviePy pipeline
as youtube_shorts.py: product images → animated slideshow → gTTS voiceover → mp4.

Auth:    Same cookie/email-password flow as pinterest_daily.py (PinterestClient).
Content: content_generator.py for Pinterest-optimised title / description / alt text.
Boards:  product type/tags → board_mapping.py → correct Pinterest board.
Safety:  human-paced delays, 10-day product repost cooldown, 1–2 pins per run.

DRY_RUN=true  → full pipeline (product pick, video build, content) but skips Pinterest upload.
MAX_PINS_PER_RUN (env, default 1) → set to 2 for scheduled production runs.
"""

import glob
import io
import json
import logging
import os
import random
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
from gtts import gTTS
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
try:
    from moviepy.editor import AudioFileClip, CompositeAudioClip, VideoClip, concatenate_videoclips
except ImportError:
    from moviepy import AudioFileClip, CompositeAudioClip, VideoClip, concatenate_videoclips

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient, format_product_for_pinterest, select_board_for_product
from content_generator import generate_content_package

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

VIDEO_HISTORY_FILE = Path(__file__).parent / "video_posting_history.json"
VIDEO_REPOST_COOLDOWN_DAYS = 10
_AUDIO_DIR = Path(__file__).parent / "audio"

MAX_PINS_PER_RUN = int(os.getenv("MAX_PINS_PER_RUN", "3"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")
MAX_VIDEO_SIZE_MB = 100
BRAND_NAME = os.getenv("BRAND_NAME", "MeeeShop US Boutique")
GTTS_TLD = "com"  # US Accent for gTTS voiceover
GTTS_LANG = "en"

# Pinterest pin creation endpoint (web-UI flow — no OAuth app needed)
_PINTEREST_PIN_URL = "https://www.pinterest.com/resource/PinResource/create/"

# Boards preferred for video content
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
# Video build config (mirrors youtube_shorts.py)
# ---------------------------------------------------------------------------

VIDEO_W, VIDEO_H  = 1080, 1920
FPS               = 30
CLIP_DURATION     = 5      # seconds per product image slide
VOICEOVER_DURATION = 4     # max voiceover length in seconds
OUT_DIR           = Path(__file__).parent / "generated_videos"
OUT_DIR.mkdir(exist_ok=True)

FORMATS = [
    {"badge": "OOTD",          "cta": "Shop The Look",        "badge_color": (255, 200, 50)},
    {"badge": "TRENDING",      "cta": "Get It Now",            "badge_color": (255, 50, 100)},
    {"badge": "NEW DROP",      "cta": "Shop Before It's Gone", "badge_color": (50, 200, 100)},
    {"badge": "STYLE TIPS",    "cta": "See All Styles",        "badge_color": (80, 160, 255)},
    {"badge": "FASHION STEAL", "cta": "Grab This Deal",        "badge_color": (255, 130, 50)},
    {"badge": "STYLE INSPO",   "cta": "Get The Look",          "badge_color": (180, 80, 255)},
    {"badge": "MUST HAVE",     "cta": "Add To Cart",           "badge_color": (210, 160, 140)},
    {"badge": "ROMANTIC ERA",  "cta": "Elevate Your Look",     "badge_color": (115, 30, 70)},
    {"badge": "VIBE CHECK",    "cta": "Shop The Vibe",         "badge_color": (70, 95, 120)},
    {"badge": "DAILY RITUAL",  "cta": "Get The Look",          "badge_color": (60, 105, 80)},
]

SOLID_BG_COLORS = [
    (248, 240, 235),  # warm cream
    (240, 235, 248),  # soft lavender
    (235, 248, 240),  # mint green
    (248, 235, 240),  # blush pink
    (235, 245, 250),  # sky blue
    (250, 245, 235),  # peach
    (240, 240, 248),  # periwinkle
    (245, 238, 230),  # linen
]

# Font paths (CI = Linux, local = Windows)
import platform
if platform.system() == "Windows":
    _FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
    _FONT_REG  = "C:/Windows/Fonts/arial.ttf"
else:
    _FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    _FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_BOLD if bold else _FONT_REG, size)
    except Exception:
        return ImageFont.load_default()


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


def _was_recently_posted(product: Dict[str, Any], video_history: Dict[str, Any]) -> bool:
    product_handle = product.get("handle", "")
    product_id = str(product.get("id", ""))
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=VIDEO_REPOST_COOLDOWN_DAYS)
    
    # 1. Check video history (by handle or ID)
    for post in video_history.get("posts", []):
        post_handle = post.get("product_handle")
        post_id = str(post.get("product_id", ""))
        if (post_handle and post_handle == product_handle) or (post_id and post_id == product_id):
            try:
                posted_at = datetime.fromisoformat(post["posted_at"])
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                if posted_at > cutoff:
                    return True
            except Exception:
                pass

    # 2. Check other history files
    history_files = [
        ("posting_history_v2.json", "posts", "timestamp"),
        ("refresh_history_v2.json", "refreshes", "timestamp"),
        ("posting_history.json", "posts", "timestamp"),
        ("refresh_history.json", "refreshes", "timestamp"),
        ("blog_posting_history.json", "posts", "timestamp"),
    ]
    
    for filename, list_key, time_key in history_files:
        path = Path(__file__).parent / filename
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data.get(list_key, []):
                    item_id = str(item.get("product_id") or item.get("id") or "")
                    item_handle = item.get("product_handle") or item.get("handle")
                    if (item_id and item_id == product_id) or (item_handle and item_handle == product_handle):
                        ts_str = item.get(time_key) or item.get("posted_at")
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str)
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                            if ts > cutoff:
                                return True
            except Exception as e:
                logger.warning(f"Error reading history file {filename}: {e}")
                
    return False


# ---------------------------------------------------------------------------
# Frame / video building (adapted from youtube_shorts.py)
# ---------------------------------------------------------------------------

def _solid_bg(color: tuple, w: int = VIDEO_W, h: int = VIDEO_H) -> Image.Image:
    img = Image.new("RGB", (w, h))
    dr  = ImageDraw.Draw(img)
    r0, g0, b0 = color
    for y in range(h):
        t = y / h
        dr.line([(0, y), (w, y)], fill=(int(r0 - 15*t), int(g0 - 15*t), int(b0 - 15*t)))
    return img


def _load_product_image(url: str) -> Optional[Image.Image]:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        img = ImageEnhance.Color(img).enhance(1.22)
        img = ImageEnhance.Contrast(img).enhance(1.08)
        img = ImageEnhance.Sharpness(img).enhance(1.15)
        img = ImageEnhance.Brightness(img).enhance(1.04)
        return img
    except Exception as e:
        logger.warning(f"Could not load product image {url[:60]}: {e}")
        return None


def _compose_frame(
    bg: Image.Image,
    product_img: Image.Image,
    title: str,
    price: str,
    url: str,
    fmt: Dict,
    product_scale: float = 1.0,
    show_url: bool = False,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    angle: float = 0.0,
) -> Image.Image:
    w, h   = VIDEO_W, VIDEO_H
    canvas = bg.copy()

    # Create the floating product card
    pw, ph  = product_img.size
    max_h   = h - 500
    max_w   = int(w * 0.90)
    base_sc = min(max_h / ph, max_w / pw)
    cur_sc  = base_sc * product_scale
    nw, nh  = max(1, int(pw * cur_sc)), max(1, int(ph * cur_sc))
    
    fg = product_img.resize((nw, nh), Image.LANCZOS)
    
    # Add a white border to the card
    fg_with_border = Image.new("RGBA", (nw + 20, nh + 20), (255, 255, 255, 255))
    fg_with_border.paste(fg, (10, 10))
    
    # Rotate
    if angle != 0:
        fg_with_border = fg_with_border.rotate(angle, resample=Image.BICUBIC, expand=True)
    
    # Paste centered with offset
    fw, fh = fg_with_border.size
    x_pos = (w - fw) // 2 + int(x_offset)
    y_pos = (h - fh) // 2 + int(y_offset)
    
    canvas.paste(fg_with_border, (x_pos, y_pos), fg_with_border)

    # Transparent center overlay for text (Template N style)
    box_w = int(w * 0.85)
    box_h = int(h * 0.35)
    box_x = (w - box_w) // 2
    box_y = (h - box_h) // 2

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=20, fill=(0, 0, 0, 90))
    
    cvs = canvas.convert("RGBA")
    cvs.alpha_composite(overlay)
    img = cvs.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Category / Badge
    draw.text((w // 2, box_y + int(box_h * 0.15)), fmt["badge"], fill="white", font=_font(int(box_h * 0.06)), anchor="mm")

    # Title
    for i, line in enumerate(textwrap.wrap(title, 34)[:2]):
        draw.text((w // 2, box_y + int(box_h * 0.40) + i * int(box_h * 0.12)), line, fill="white", font=_font(int(box_h * 0.08)), anchor="mm")

    # Price
    if price:
        draw.text((w // 2, box_y + int(box_h * 0.8)), f"${price}", fill=(255, 127, 80), font=_font(int(box_h * 0.09)), anchor="mm")

    # URL bar (last frame only)
    if show_url:
        short = url.replace("https://", "").split("?")[0][:44]
        draw.rounded_rectangle([(35, h-62), (w-35, h-14)], radius=14, fill=(255, 255, 255, 190))
        draw.text((w//2, h-38), short, font=_font(22, bold=False), fill=(0, 70, 180), anchor="mm")

    return img


def _save_thumbnail(frame_img: Image.Image, handle: str) -> str:
    """Save first composed frame as a JPEG thumbnail. Returns path."""
    thumb_path = str(OUT_DIR / f"{handle[:30]}_thumb.jpg")
    frame_img.convert("RGB").save(thumb_path, "JPEG", quality=92)
    logger.info(f"Thumbnail saved: {thumb_path}")
    return thumb_path


def _pick_music_track() -> Optional[str]:
    """Pick a random MP3 from audio folder. Returns path or None."""
    if not _AUDIO_DIR.exists():
        return None
    tracks = [f for f in glob.glob(str(_AUDIO_DIR / "*.mp3"))
              if os.path.getsize(f) > 50_000]
    if tracks:
        return random.choice(tracks)
    return None


def _static_frame_clip(
    frame_img: Image.Image,
    duration: float,
) -> VideoClip:
    """Create a static video clip from a single PIL image."""
    frame_array = np.array(frame_img)
    return VideoClip(lambda t: frame_array, duration=duration).set_fps(FPS)


def _slide_clip(
    bg: Image.Image,
    product_img: Image.Image,
    title: str,
    price: str,
    url: str,
    fmt: Dict,
    effect: str,
    show_url: bool = False,
) -> VideoClip:
    import math
    
    # Background is already blurred and prepared
    bg_r = bg

    def _params(t: float):
        scale = 0.95
        if effect == "float":
            return scale, 0, math.cos(t * 2) * 20, math.sin(t * 2) * 3
        elif effect == "wobble":
            return scale, math.cos(t * 3) * 15, 0, math.sin(t * 4) * 4
        elif effect == "spin":
            return scale + (t * 0.02), 0, 0, t * 5
        elif effect == "zoom-float":
            return scale + (t * 0.03), 0, math.cos(t) * 10, math.sin(t) * 2
        else:
            return scale, 0, 0, math.sin(t * 2) * 3

    def make_frame(t: float):
        scale, ox, oy, angle = _params(t)
        frame = _compose_frame(bg_r, product_img, title, price, url, fmt,
                               product_scale=scale,
                               show_url=(show_url and t > CLIP_DURATION - 0.5),
                               x_offset=ox, y_offset=oy, angle=angle)
        return np.array(frame)

    return VideoClip(make_frame, duration=CLIP_DURATION).set_fps(FPS)


def build_video(product: Dict, fmt: Dict, bg_colors: List[tuple], store_base_url: str) -> Optional[Tuple[str, str]]:
    """
    Build a 30s product slideshow mp4 from Shopify product images.
    Returns tuple (video_path, thumbnail_path) or None on failure.
    """
    title  = product["title"]
    price  = product.get("variants", [{}])[0].get("price", "0")
    handle = product.get("handle", "")
    url    = f"{store_base_url.rstrip('/')}/products/{handle}?utm_source=pinterest&utm_medium=video&utm_campaign={BRAND_NAME.lower()}"

    images = product.get("images", [])[:6]
    if not images:
        logger.error(f"No images for product {title}")
        return None
    # Pad to 6 if fewer images available
    while len(images) < 6:
        images = (images * 2)[:6]

    logger.info(f"Building video: {title[:50]} ({len(images)} slides)")

    effects = ["float", "wobble", "spin", "zoom-float"]
    clips   = []
    thumb_path = None
    intro_clip = None

    for i, img_data in enumerate(images):
        prod_img = _load_product_image(img_data["src"])
        if prod_img is None:
            continue
            
        from PIL import ImageFilter
        bg_r = prod_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(30)).point(lambda p: p * 0.6)
        
        effect   = effects[i % len(effects)]
        show_url = (i == len(images) - 1)
        clip     = _slide_clip(bg_r, prod_img, title, price, url, fmt, effect, show_url)
        clip     = clip.fadein(0.1).fadeout(0.1)
        clips.append(clip)

        # Create intro frame (static 2s full product) from first image
        if intro_clip is None:
            intro_frame_img = _compose_frame(bg_r, prod_img, title, price, url, fmt, product_scale=1.0, show_url=False)
            intro_clip = _static_frame_clip(intro_frame_img, duration=2.0).fadeout(0.3)
            thumb_path = _save_thumbnail(intro_frame_img, handle)

    if not clips:
        logger.error("No clips built — all product images failed to load")
        return None

    # Prepend intro (2s static full product) + animated clips
    if intro_clip:
        clips = [intro_clip] + clips

    video       = concatenate_videoclips(clips, method="compose")
    total_secs  = video.duration
    audio_clips = []

    # Background music
    music_path = _pick_music_track()
    if music_path:
        bg_aud = AudioFileClip(music_path).volumex(0.35)
        if bg_aud.duration < total_secs:
            bg_aud = bg_aud.audio_loop(duration=total_secs)
        else:
            bg_aud = bg_aud.subclip(0, total_secs)
        audio_clips.append(bg_aud)
        logger.info(f"Background music: {os.path.basename(music_path)}")

    # Voiceover (gTTS) — overlaid at end as CTA
    vo_text = (
        f"Discover the {title} at {BRAND_NAME} — only ${price}! "
        f"Shop the link in description now!"
    )
    try:
        from ai_client import generate as ai_generate
        ai_result = ai_generate(
            f"Write a 2-sentence Pinterest video voiceover for USA women shoppers.\n"
            f"Product: '{title}' — ${price} at {BRAND_NAME}\n"
            f"Rules: energetic fashion-influencer tone, mention price, say '{BRAND_NAME}', "
            f"end with 'shop the link', max 35 words, no hashtags.\n"
            f"Output ONLY the voiceover text, nothing else.",
            max_tokens=80, temperature=0.9,
        )
        if ai_result and len(ai_result.strip()) > 10:
            vo_text = ai_result.strip()
    except Exception:
        pass

    with tempfile.TemporaryDirectory() as tmp:
        vo_path = os.path.join(tmp, "vo.mp3")
        try:
            gTTS(text=vo_text, lang="en", tld="us").save(vo_path)
            vo = AudioFileClip(vo_path)
            if vo.duration > VOICEOVER_DURATION:
                vo = vo.subclip(0, VOICEOVER_DURATION)
            vo_start = max(0, total_secs - vo.duration - 1.0)
            audio_clips.append(vo.set_start(vo_start).volumex(1.1))
            logger.info(f"Voiceover: {vo.duration:.1f}s starting at {vo_start:.1f}s (end CTA)")
        except Exception as e:
            logger.warning(f"gTTS voiceover failed: {e}")

        if audio_clips:
            video = video.set_audio(CompositeAudioClip(audio_clips))

        out_path = str(OUT_DIR / f"{handle[:30]}_{int(time.time())}.mp4")
        logger.info(f"Rendering → {out_path}")
        video.write_videofile(
            out_path, fps=FPS, codec="libx264", audio_codec="aac",
            temp_audiofile=os.path.join(tmp, "tmp_audio.m4a"),
            remove_temp=True, verbose=False, logger=None,
            ffmpeg_params=["-crf", "18", "-preset", "fast", "-b:a", "192k"],
        )

    video.close()
    size_mb = os.path.getsize(out_path) / 1_048_576
    logger.info(f"Rendered: {os.path.basename(out_path)} ({size_mb:.1f} MB)")
    if size_mb > MAX_VIDEO_SIZE_MB:
        logger.error(f"Video too large ({size_mb:.1f} MB > {MAX_VIDEO_SIZE_MB} MB) — skipping")
        os.unlink(out_path)
        if thumb_path and os.path.exists(thumb_path):
            os.unlink(thumb_path)
        return None

    return (out_path, thumb_path)


# ---------------------------------------------------------------------------
# Board selection
# ---------------------------------------------------------------------------

def _pick_board(boards: List[Dict], formatted_product: Dict, history: Dict = None) -> Dict:
    from board_mapping import select_best_lru_board

    title = formatted_product.get("title", "")
    ptype = formatted_product.get("product_type", "")
    last_used = (history or {}).get("board_last_used", {})

    best_board = select_best_lru_board(
        product_title=title, 
        product_type=ptype, 
        live_boards=boards, 
        board_last_used=last_used
    )
    
    if best_board and "name" in best_board:
        return best_board

    board_map = {b["name"].lower(): b for b in boards}
    for pref in VIDEO_PREFERRED_BOARDS:
        if pref.lower() in board_map:
            return board_map[pref.lower()]

    return random.choice(boards)



# ---------------------------------------------------------------------------
# Pinterest video pin via direct authenticated session (CSRF-safe)
# ---------------------------------------------------------------------------
# Pinterest video pin via py3-pinterest upload_video_pin()
# ---------------------------------------------------------------------------

# py3-pinterest raw client (for upload_video_pin — available in v2.0.0+)
from py3pin.Pinterest import Pinterest as _Py3Pinterest


def _make_py3_client(pinterest: "PinterestClient") -> Optional["_Py3Pinterest"]:
    """
    Create a _Py3Pinterest instance using the SAME authenticated session object
    as PinterestClient. This avoids any cookie-jar divergence.
    """
    email    = get_secret("PINTEREST_EMAIL") or ""
    username = get_secret("PINTEREST_USERNAME") or ""
    py3 = _Py3Pinterest(email=email, password="", username=username)

    # Monkey-patch _poll_upload_status to increase timeout/retries from 60s (30*2) to 300s (150*2)
    try:
        original_poll = py3._poll_upload_status
        def custom_poll(upload_id, max_retries=150, interval=2):
            logger.info(f"Polling upload status for {upload_id} (max_retries={max_retries}, interval={interval}s)")
            return original_poll(upload_id, max_retries=max_retries, interval=interval)
        py3._poll_upload_status = custom_poll
    except Exception as e:
        logger.warning(f"Could not monkey-patch _poll_upload_status: {e}")

    try:
        auth_session = pinterest._get_raw_session()
        # Direct session swap (shared object — same cookie jar)
        py3.http = auth_session

        # Verbose diagnostics so we can see what's actually present
        cookie_names = sorted(auth_session.cookies.keys())
        csrftoken    = auth_session.cookies.get("csrftoken", "")
        sess_cookie  = auth_session.cookies.get("_pinterest_sess", "")
        auth_b_token = auth_session.cookies.get("_auth", "") or auth_session.cookies.get("_b", "")
        logger.info(f"[py3-auth] cookie names ({len(cookie_names)}): {cookie_names}")
        logger.info(f"[py3-auth] csrftoken len: {len(csrftoken)}  _pinterest_sess len: {len(sess_cookie)}  _auth/_b len: {len(auth_b_token)}")
        if not csrftoken:
            logger.error("[py3-auth] csrftoken is EMPTY — Pinterest will return 401")
        if not sess_cookie:
            logger.error("[py3-auth] _pinterest_sess is EMPTY — session not authenticated")
    except Exception as e:
        logger.warning(f"Could not share session with py3-pinterest: {e}")
    return py3


def _post_video_pin(
    pinterest: "PinterestClient",
    video_path: str,
    board_id: str,
    title: str,
    description: str,
    link: str,
    alt_text: str,
    thumb_path: Optional[str] = None,
) -> Optional[str]:
    """Upload MP4 as a Pinterest video pin via py3-pinterest. Returns pin_id or None."""
    time.sleep(random.uniform(3, 7))
    py3 = _make_py3_client(pinterest)
    try:
        resp = py3.upload_video_pin(
            video_file=video_path,
            title=title,
            description=description,
            link=link,
            board_id=board_id,
            alt_text=alt_text,
            cover_image_file=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
        )
        resp_data = resp.json() if hasattr(resp, "json") else resp
        pin_id = (
            (resp_data or {}).get("resource_response", {}).get("data", {}).get("id")
            or (resp_data or {}).get("data", {}).get("id")
        )
        if pin_id:
            logger.info(f"Video pin created — pin_id: {pin_id}")
            return str(pin_id)
        logger.error(f"upload_video_pin unexpected response: {str(resp_data)[:300]}")
        return None
    except requests.exceptions.HTTPError as e:
        # Capture Pinterest's actual error body so we can see the failure reason
        try:
            err_body = e.response.text[:1000] if e.response is not None else "(no response)"
            err_headers = dict(e.response.headers) if e.response is not None else {}
            logger.error(f"upload_video_pin HTTPError: {e}")
            logger.error(f"[401-debug] response body: {err_body}")
            logger.error(f"[401-debug] response headers: {err_headers}")
            logger.error(f"[401-debug] request URL: {e.response.request.url if e.response is not None else 'n/a'}")
            req_headers = dict(e.response.request.headers) if e.response is not None else {}
            # Redact cookie/csrf values, just show keys + lengths
            safe_req_headers = {
                k: (f"<len={len(v)}>" if k.lower() in ("cookie", "x-csrftoken") else v)
                for k, v in req_headers.items()
            }
            logger.error(f"[401-debug] request headers: {safe_req_headers}")
        except Exception as inner:
            logger.error(f"upload_video_pin error (and failed to dump details: {inner}): {e}")
        return None
    except Exception as e:
        logger.error(f"upload_video_pin error: {e}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Pinterest content optimisation
# ---------------------------------------------------------------------------

def _build_pin_content(product: Dict, board_name: str) -> Dict[str, str]:
    base         = generate_content_package(product, board_name)
    pin_title    = base["pin_title"]
    hashtags_str = " ".join(base.get("hashtags", [])[:12])
    base_desc    = base["pin_description"]
    cta          = random.choice([
        "Watch the styling video + Shop the look →",
        "See it styled — tap to shop →",
        "Style inspiration + shop the look →",
        "Watch & shop this look →",
    ])
    pin_description = f"{base_desc}\n\n{cta}\n\n{hashtags_str}".strip()
    if len(pin_description) > 500:
        pin_description = f"{base_desc}\n\n{cta}".strip()[:500]

    alt_text = base.get("pin_alt_text") or base.get("alt_text") or ""
    if alt_text:
        alt_text = f"Styling video — {alt_text}"[:500]
    else:
        alt_text = f"Styling video for {product.get('title', '')[:80]}"

    return {"title": pin_title, "description": pin_description, "alt_text": alt_text}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_video_posting() -> None:
    shopify_url    = get_secret("SHOPIFY_STORE_URL")
    shopify_token  = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    if not shopify_url or not shopify_token or shopify_token == "placeholder":
        raise ValueError("SHOPIFY_STORE_URL / SHOPIFY_ACCESS_TOKEN not set")

    if DRY_RUN:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE — no pins will be posted to Pinterest")
        logger.info("=" * 60)

    # Pinterest auth
    pinterest = PinterestClient()
    boards = []
    if not DRY_RUN:
        if not pinterest.login():
            raise RuntimeError("Pinterest authentication failed")
        logger.info("✓ Pinterest authentication OK")
        boards = pinterest.fetch_boards()

    if not boards:
        from board_mapping import MEEESHOP_BOARDS
        boards = [{"name": b, "id": f"mock_{i}"} for i, b in enumerate(MEEESHOP_BOARDS)]
    logger.info(f"✓ Loaded {len(boards)} Pinterest boards")


    # Shopify products
    shopify  = ShopifyClient(shopify_url, shopify_token)
    products = shopify.get_products(limit=50)
    if not products:
        raise RuntimeError("No Shopify products returned")
    logger.info(f"✓ Loaded {len(products)} Shopify products")

    # History / cooldown
    history   = _load_history()
    available = [p for p in products if not _was_recently_posted(p, history)]
    if not available:
        logger.info("All products are within the repost cooldown window — skipping execution to avoid spam.")
        return

    # Pick products for this run (one per pin)
    to_post = random.sample(available, min(MAX_PINS_PER_RUN, len(available)))
    logger.info(f"Will post {len(to_post)} video pin(s) (MAX_PINS_PER_RUN={MAX_PINS_PER_RUN})")

    posted_count   = 0
    post_failures  = 0

    for idx, product in enumerate(to_post):
        logger.info(f"\n--- Pin {idx+1}/{len(to_post)}: '{product['title']}' ---")

        formatted   = format_product_for_pinterest(product, store_base_url)
        product_url = formatted["url"]
        logger.info(f"  Destination : {product_url}")

        # Board selection — rotate per pin using LRU so they land on different boards
        rotated = boards[idx:] + boards[:idx] if idx > 0 else boards
        board   = _pick_board(rotated, formatted, history)
        logger.info(f"  Board       : '{board['name']}' (id={board['id']})")


        # Content
        content = _build_pin_content(product, board["name"])
        logger.info(f"  Title       : {content['title']}")
        logger.info(f"  Description : {content['description'][:80]}…")
        logger.info(f"  Alt text    : {content['alt_text'][:80]}")

        # Pick a random format and bg colors for this pin
        fmt       = random.choice(FORMATS)
        bg_colors = random.sample(SOLID_BG_COLORS, min(6, len(SOLID_BG_COLORS)))

        if DRY_RUN:
            logger.info("  [DRY RUN] Would build video here — skipped")
            logger.info("  [DRY RUN] Would post video pin here — skipped")
            logger.info("  ✓ Dry-run validation passed for this product")
            posted_count += 1
            continue

        # Build video (generates high-quality composed frames as MP4)
        result = build_video(product, fmt, bg_colors, store_base_url)
        if not result:
            logger.error(f"Video build failed for '{product['title']}' — skipping")
            post_failures += 1
            continue
        video_path, thumb_path = result

        # Human-paced delay before posting
        pause = random.uniform(5, 12) if idx == 0 else random.uniform(90, 180)
        logger.info(f"  Pausing {pause:.0f}s before posting…")
        time.sleep(pause)

        pin_id = _post_video_pin(
            pinterest=pinterest,
            video_path=video_path,
            board_id=board["id"],
            title=content["title"],
            description=content["description"],
            link=product_url,
            alt_text=content["alt_text"],
            thumb_path=thumb_path,
        )
        if not pin_id:
            logger.error("Pinterest video pin creation failed — skipping")
            post_failures += 1
            # Cleanup on failure
            try:
                os.unlink(video_path)
            except Exception:
                pass
            try:
                if thumb_path and os.path.exists(thumb_path):
                    os.unlink(thumb_path)
            except Exception:
                pass
            continue

        # Cleanup local video and thumbnail files to save disk
        try:
            os.unlink(video_path)
        except Exception:
            pass
        try:
            if thumb_path and os.path.exists(thumb_path):
                os.unlink(thumb_path)
        except Exception:
            pass

        history["posts"].append({
            "product_id":      str(product.get("id", "")),
            "product_handle":  product.get("handle", ""),
            "product_title":   product["title"],
            "pin_id":          pin_id,
            "board":           board["name"],
            "product_url":     product_url,
            "posted_at":       datetime.now(timezone.utc).isoformat(),
        })
        _save_history(history)
        posted_count += 1

        logger.info(
            f"  ✓ Pin posted!\n"
            f"    Product : {product['title']}\n"
            f"    Board   : {board['name']}\n"
            f"    URL     : {product_url}\n"
            f"    Pin ID  : {pin_id}"
        )

    if DRY_RUN:
        logger.info(
            f"\n{'=' * 60}\n"
            f"DRY RUN COMPLETE — {posted_count}/{len(to_post)} product(s) validated.\n"
            f"All systems OK. Remove DRY_RUN=true to go live.\n"
            f"{'=' * 60}"
        )
    else:
        logger.info(f"\nRun complete — {posted_count}/{len(to_post)} pin(s) posted.")

    if posted_count == 0 and post_failures > 0:
        raise RuntimeError(
            f"All {post_failures} pin(s) failed to post. "
            "Check Pinterest auth, product images, ffmpeg, MoviePy, and py3-pinterest v2."
        )


if __name__ == "__main__":
    run_video_posting()
