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

VIDEO_PREFERRED_BOARDS = [
    "Trends",
    "New",
    "Trends",
    "New",
    "Best selling products",
    "Outfit Ideas",
    "Style Ideas",
    "Everyday Style",
    "Chic & Effortless Styles",
    "Ootd #ootd",
]

# ---------------------------------------------------------------------------
# Video build config (mirrors youtube_shorts.py)
# ---------------------------------------------------------------------------

VIDEO_W, VIDEO_H  = 1080, 1920
FPS               = 30
CLIP_DURATION     = 2.8    # seconds per product image slide (allows shoppers to read fit/anatomy details)
VOICEOVER_DURATION = 11    # synchronized voiceover duration in seconds
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


def _font(size: int, bold: bool = True, script: bool = False, serif: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    if script or italic:
        candidates = [
            "C:/Windows/Fonts/georgiai.ttf",
            "C:/Windows/Fonts/timesi.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        ]
    elif serif:
        candidates = [
            "C:/Windows/Fonts/georgia.ttf",
            "C:/Windows/Fonts/times.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        ]
    else:
        candidates = [
            _FONT_BOLD if bold else _FONT_REG,
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
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


# ── Smooth Curved Arrow Helper for 1080x1920 Video ──────────────────────────

def _draw_video_curved_arrow(
    draw: ImageDraw.Draw,
    start_pt: Tuple[int, int],
    control_pt: Tuple[int, int],
    end_pt: Tuple[int, int],
    color: Tuple[int, int, int] = (255, 255, 255),
    width: int = 4,
):
    """Draw smooth quadratic bezier curve with an arrowhead on 1080x1920 video frame."""
    import math
    num_steps = 25
    points = []
    for i in range(num_steps + 1):
        t = i / float(num_steps)
        x = ((1 - t) ** 2) * start_pt[0] + 2 * (1 - t) * t * control_pt[0] + (t ** 2) * end_pt[0]
        y = ((1 - t) ** 2) * start_pt[1] + 2 * (1 - t) * t * control_pt[1] + (t ** 2) * end_pt[1]
        points.append((x, y))

    # Dark halo for contrast
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)]:
        halo_pts = [(x + dx, y + dy) for x, y in points]
        draw.line(halo_pts, fill=(10, 10, 14, 230), width=width + 3)

    draw.line(points, fill=color, width=width)

    # Arrowhead at end_pt
    p_prev = points[-4]
    dx = end_pt[0] - p_prev[0]
    dy = end_pt[1] - p_prev[1]
    angle = math.atan2(dy, dx)
    arrow_len = 22
    arrow_angle = math.pi / 5.5

    a1 = (end_pt[0] - arrow_len * math.cos(angle - arrow_angle), end_pt[1] - arrow_len * math.sin(angle - arrow_angle))
    a2 = (end_pt[0] - arrow_len * math.cos(angle + arrow_angle), end_pt[1] - arrow_len * math.sin(angle + arrow_angle))

    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        draw.polygon([(end_pt[0] + dx, end_pt[1] + dy), (a1[0] + dx, a1[1] + dy), (a2[0] + dx, a2[1] + dy)], fill=(10, 10, 14, 230))

    draw.polygon([end_pt, a1, a2], fill=color)


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
    slide_idx: int = 0,
    total_slides: int = 4,
    highlights: Optional[Dict] = None,
) -> Image.Image:
    """
    Compose 9:16 vertical video frame (1080x1920) with frame-by-frame feature breakdown:
    - Scene 0: Brand Hook & Full Lookbook Title
    - Scene 1: Fit & Waistline Focus with Arrow Callout
    - Scene 2: Fabric & Stretch Focus with Arrow Callout
    - Scene 3+: Social Proof, Shipping Offer & Final Shop CTA
    """
    w, h   = VIDEO_W, VIDEO_H
    canvas = bg.copy()

    pw, ph  = product_img.size
    base_sc = max(h / ph, w / pw)
    cur_sc  = base_sc * product_scale
    nw, nh  = max(1, int(pw * cur_sc)), max(1, int(ph * cur_sc))
    
    fg = product_img.resize((nw, nh), Image.LANCZOS)
    if angle != 0:
        fg = fg.rotate(angle, resample=Image.BICUBIC, expand=True)
    
    fw, fh = fg.size
    x_pos = (w - fw) // 2 + int(x_offset)
    y_pos = (h - fh) // 2 + int(y_offset)
    
    if fg.mode == "RGBA":
        canvas.paste(fg, (x_pos, y_pos), fg)
    else:
        canvas.paste(fg, (x_pos, y_pos))

    # RGBA overlay for frosted pills and gradient vignettes
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    # Top gradient vignette (0..200)
    for i in range(200):
        progress = 1.0 - (i / 200.0)
        alpha = int(120 * (progress ** 1.4))
        ov_draw.line([(0, i), (w, i)], fill=(10, 10, 14, alpha))

    # Bottom gradient vignette (1450..1920)
    v_start = 1450
    v_h = h - v_start
    for i in range(v_h):
        progress = i / float(v_h)
        alpha = int(220 * (progress ** 1.3))
        ov_draw.line([(0, v_start + i), (w, v_start + i)], fill=(10, 10, 14, alpha))

    CREAM_WHITE    = (255, 255, 255, 255)
    CHAMPAGNE_GOLD = (255, 230, 130, 255)
    WARM_OAT       = (255, 245, 225, 255)
    FROSTED_GLASS  = (15, 15, 20, 210)
    SHADOW_DARK    = (5, 5, 8, 250)

    def draw_bold_shadowed(d, pos, text, font, fill=CREAM_WHITE, anchor="mm"):
        x, y = pos
        for dx, dy in [(-3,0), (3,0), (0,-3), (0,3), (-2,-2), (2,2), (-2,2), (2,-2), (-1,-1), (1,1)]:
            d.text((x + dx, y + dy), text, fill=SHADOW_DARK, font=font, anchor=anchor)
        d.text((x, y), text, fill=fill, font=font, anchor=anchor)

    def draw_video_pill(d, x, y, title_text, desc_text, align="left"):
        t_font = _font(34, bold=True)
        d_font = _font(26, bold=False)
        t_box = t_font.getbbox(title_text)
        d_box = d_font.getbbox(desc_text)
        t_w = t_box[2] - t_box[0]
        d_w = d_box[2] - d_box[0]
        max_w = max(t_w, d_w)
        pad_x, pad_y = 28, 16
        card_w = max_w + pad_x * 2
        card_h = (t_box[3] - t_box[1]) + (d_box[3] - d_box[1]) + pad_y * 2 + 10
        
        if align == "right":
            rx1 = x - card_w
            rx2 = x
        elif align == "center":
            rx1 = x - card_w // 2
            rx2 = x + card_w // 2
        else:
            rx1 = x
            rx2 = x + card_w
            
        ry1 = y
        ry2 = y + card_h
        
        # Rounded pill
        r = 18
        d.rounded_rectangle([rx1, ry1, rx2, ry2], radius=r, fill=FROSTED_GLASS)
        
        if align == "right":
            d.text((rx2 - pad_x, ry1 + pad_y), title_text, fill=CREAM_WHITE, font=t_font, anchor="ra")
            d.text((rx2 - pad_x, ry1 + pad_y + 40), desc_text, fill=WARM_OAT, font=d_font, anchor="ra")
        elif align == "center":
            d.text((rx1 + card_w // 2, ry1 + pad_y), title_text, fill=CREAM_WHITE, font=t_font, anchor="ma")
            d.text((rx1 + card_w // 2, ry1 + pad_y + 40), desc_text, fill=WARM_OAT, font=d_font, anchor="ma")
        else:
            d.text((rx1 + pad_x, ry1 + pad_y), title_text, fill=CREAM_WHITE, font=t_font)
            d.text((rx1 + pad_x, ry1 + pad_y + 40), desc_text, fill=WARM_OAT, font=d_font)
            
        return (rx1, ry1, rx2, ry2)

    clean_title = (title or "").strip()
    for leak in ["we need", "create a", "product:", "type:"]:
        if leak in clean_title.lower():
            clean_title = "Trending Boutique Style"
            break

    price_str = f"${float(str(price).replace('$', '')):.2f}" if price and any(c.isdigit() for c in str(price)) else ""

    if not highlights:
        try:
            from content_generator_v2 import generate_product_fit_highlights
            highlights = generate_product_fit_highlights({"title": title, "product_type": "Fashion"})
        except Exception:
            highlights = {}

    # ── SCENE 0: INTRO HOOK ──────────────────────────────────────────────────
    if slide_idx == 0:
        # Top Hook
        draw_bold_shadowed(ov_draw, (w // 2, 140), "M E E E S H O P  •  N E W  A R R I V A L S", _font(30, bold=True), fill=CHAMPAGNE_GOLD, anchor="mm")
        
        # Product Headline (Wrapped)
        title_lines = textwrap.wrap(clean_title.upper(), width=26)[:2]
        for idx_l, t_line in enumerate(title_lines):
            draw_bold_shadowed(ov_draw, (w // 2, 220 + idx_l * 56), t_line, _font(48, bold=True), fill=CREAM_WHITE, anchor="mm")

        # Bottom Bar: Price & Fit Guarantee
        sub_text = f"{price_str}   •   FREE US SHIPPING   •   TRUE-TO-SIZE FIT" if price_str else "FREE US SHIPPING   •   TRUE-TO-SIZE FIT"
        draw_bold_shadowed(ov_draw, (w // 2, 1680), sub_text, _font(36, bold=True), fill=WARM_OAT, anchor="mm")

        # CTA Pill
        cta_btn_w, cta_btn_h = 720, 82
        bx1 = (w - cta_btn_w) // 2
        by1 = 1760
        ov_draw.rounded_rectangle([bx1, by1, bx1 + cta_btn_w, by1 + cta_btn_h], radius=cta_btn_h // 2, fill=(255, 255, 255, 250))
        ov_draw.text((w // 2, by1 + 22), "SHOP THE LOOK  →  US.MEEESHOP.COM", fill=(15, 15, 20, 255), font=_font(32, bold=True), anchor="mm")

    # ── SCENE 1: FIT & SILHOUETTE FOCUS ──────────────────────────────────────
    elif slide_idx == 1:
        # Top Tag
        ov_draw.rounded_rectangle([60, 110, 520, 175], radius=32, fill=FROSTED_GLASS)
        ov_draw.text((290, 142), "★  FIT & SILHOUETTE FOCUS", fill=CHAMPAGNE_GOLD, font=_font(26, bold=True), anchor="mm")

        # Waist Callout Pill
        c1 = highlights.get("callout_waist", {})
        t1_title = c1.get("title", "Contour Waistband")
        t1_desc = c1.get("desc", "Slimming panels that hug your natural curves")
        p1 = draw_video_pill(ov_draw, 480, 480, t1_title, t1_desc, align="left")
        _draw_video_curved_arrow(ov_draw, start_pt=(p1[0] + 40, p1[3]), control_pt=(560, 620), end_pt=(530, 640), color=(255, 255, 255))

        # Bottom Bar
        draw_bold_shadowed(ov_draw, (w // 2, 1720), "DESIGNED FOR A FLATTERING, CONFIDENT FIT", _font(34, bold=True), fill=WARM_OAT, anchor="mm")
        draw_bold_shadowed(ov_draw, (w // 2, 1780), "US.MEEESHOP.COM  •  FAST US DELIVERY", _font(28, bold=True), fill=CREAM_WHITE, anchor="mm")

    # ── SCENE 2: FABRIC & CRAFTSMANSHIP FOCUS ────────────────────────────────
    elif slide_idx == 2:
        # Top Tag
        ov_draw.rounded_rectangle([60, 110, 560, 175], radius=32, fill=FROSTED_GLASS)
        ov_draw.text((310, 142), "★  PREMIUM FABRIC & STRETCH", fill=CHAMPAGNE_GOLD, font=_font(26, bold=True), anchor="mm")

        # Fabric Callout Pill
        c4 = highlights.get("callout_fabric", {})
        t4_title = c4.get("title", "Ultra-Stretch Comfort Blend")
        t4_desc = c4.get("desc", "Moves with you all day with zero bagging")
        p2 = draw_video_pill(ov_draw, 140, 880, t4_title, t4_desc, align="left")
        _draw_video_curved_arrow(ov_draw, start_pt=(p2[2] - 30, p2[1] + 30), control_pt=(720, 940), end_pt=(680, 980), color=(255, 255, 255))

        # Bottom Bar
        draw_bold_shadowed(ov_draw, (w // 2, 1720), "BREATHABLE ALL-DAY LUXE COMFORT", _font(34, bold=True), fill=WARM_OAT, anchor="mm")
        draw_bold_shadowed(ov_draw, (w // 2, 1780), "US.MEEESHOP.COM  •  7-DAY EASY RETURNS", _font(28, bold=True), fill=CREAM_WHITE, anchor="mm")

    # ── SCENE 3+: SOCIAL PROOF & FINAL OFFER CTA ─────────────────────────────
    else:
        # Top Tag
        ov_draw.rounded_rectangle([60, 110, 480, 175], radius=32, fill=FROSTED_GLASS)
        ov_draw.text((270, 142), "★ ★ ★ ★ ★  BESTSELLER", fill=CHAMPAGNE_GOLD, font=_font(26, bold=True), anchor="mm")

        # Center Offer Card
        draw_video_pill(ov_draw, w // 2, 1460, "Fast & Free US Shipping", "Easy 7-Day Hassle-Free Returns & Exchanges", align="center")

        # Big CTA Pill
        cta_btn_w, cta_btn_h = 760, 88
        bx1 = (w - cta_btn_w) // 2
        by1 = 1730
        ov_draw.rounded_rectangle([bx1, by1, bx1 + cta_btn_w, by1 + cta_btn_h], radius=cta_btn_h // 2, fill=(255, 255, 255, 250))
        ov_draw.text((w // 2, by1 + 24), "TAP TO SHOP YOUR SIZE  →  US.MEEESHOP.COM", fill=(15, 15, 20, 255), font=_font(30, bold=True), anchor="mm")

    # Composite overlay onto canvas
    img = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
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
    slide_idx: int = 0,
    total_slides: int = 4,
    highlights: Optional[Dict] = None,
) -> VideoClip:
    import math
    bg_r = bg

    def _params(t: float):
        scale = 1.05
        ox, oy = 0, 0
        progress = t / CLIP_DURATION
        
        if effect == "zoom_in":
            scale = 1.0 + (progress * 0.1)
        elif effect == "zoom_out":
            scale = 1.1 - (progress * 0.1)
        elif effect == "slide_left":
            ox = 50 - (progress * 100)
        elif effect == "slide_right":
            ox = -50 + (progress * 100)
        elif effect == "slide_up":
            oy = 50 - (progress * 100)
        elif effect == "slide_down":
            oy = -50 + (progress * 100)
            
        return scale, ox, oy, 0

    def make_frame(t: float):
        scale, ox, oy, angle = _params(t)
        frame = _compose_frame(
            bg_r, product_img, title, price, url, fmt,
            product_scale=scale,
            show_url=show_url,
            x_offset=ox, y_offset=oy, angle=angle,
            slide_idx=slide_idx,
            total_slides=total_slides,
            highlights=highlights,
        )
        return np.array(frame)

    return VideoClip(make_frame, duration=CLIP_DURATION).set_fps(FPS)


def build_video(product: Dict, fmt: Dict, bg_colors: List[tuple], store_base_url: str) -> Optional[Tuple[str, str]]:
    """
    Build a multi-scene feature-progression product video (9:16 vertical 1080x1920) with audio & voiceover.
    Returns tuple (video_path, thumbnail_path) or None on failure.
    """
    title  = product["title"]
    price  = product.get("variants", [{}])[0].get("price", "0")
    handle = product.get("handle", "")
    url    = f"{store_base_url.rstrip('/')}/products/{handle}?utm_source=pinterest&utm_medium=video&utm_campaign={BRAND_NAME.lower()}"

    images = product.get("images", [])
    if not images:
        logger.error(f"No images for product {title}")
        return None

    try:
        from content_generator_v2 import generate_product_fit_highlights
        highlights = generate_product_fit_highlights(product)
    except Exception:
        highlights = {}

    logger.info(f"Building multi-scene feature video: {title[:50]} ({len(images)} slides)")

    clips   = []
    thumb_path = None

    for i, img_data in enumerate(images[:4]):
        prod_img = _load_product_image(img_data["src"])
        if prod_img is None:
            continue
            
        from PIL import ImageFilter
        bg_r = prod_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(30)).point(lambda p: p * 0.6)
        
        effects  = ["zoom_in", "zoom_out", "slide_left", "slide_right", "slide_up", "slide_down"]
        effect   = effects[i % len(effects)]
        show_url = (i == len(images[:4]) - 1)
        clip     = _slide_clip(bg_r, prod_img, title, price, url, fmt, effect, show_url, slide_idx=i, total_slides=min(4, len(images)), highlights=highlights)
        clips.append(clip)

        if thumb_path is None:
            intro_frame_img = _compose_frame(bg_r, prod_img, title, price, url, fmt, product_scale=1.0, show_url=False, slide_idx=0, total_slides=len(images), highlights=highlights)
            thumb_path = _save_thumbnail(intro_frame_img, handle)

    if not clips:
        logger.error("No clips built — all product images failed to load")
        return None

    import math
    if clips and (len(clips) * CLIP_DURATION) < 5.0:
        loops = int(math.ceil(5.0 / (len(clips) * CLIP_DURATION)))
        clips = clips * loops

    video = concatenate_videoclips(clips, method="compose")
    total_secs = video.duration

    with tempfile.TemporaryDirectory() as tmp:
        audio_clips = []
        music_track = _pick_music_track()
        if music_track and os.path.exists(music_track):
            try:
                bg_m = AudioFileClip(music_track)
                if bg_m.duration < total_secs:
                    n_loops = int(math.ceil(total_secs / bg_m.duration)) + 1
                    from moviepy.editor import concatenate_audioclips
                    bg_m = concatenate_audioclips([bg_m] * n_loops)
                bg_m = bg_m.subclip(0, total_secs).volumex(0.28)
                audio_clips.append(bg_m)
                logger.info(f"Music track mixed: {os.path.basename(music_track)}")
            except Exception as e:
                logger.warning(f"Music load failed: {e}")

        # Natural Influencer Voiceover synchronized with fit & benefits
        vo_path = os.path.join(tmp, "voiceover.mp3")
        c1 = highlights.get("callout_waist", {})
        c4 = highlights.get("callout_fabric", {})
        waist_benefit = c1.get("title", "contour waistband")
        fabric_benefit = c4.get("title", "premium stretch comfort")

        vo_text = (
            f"Check out the new {title} at MeeeShop. "
            f"Designed with a {waist_benefit} and {fabric_benefit} that moves with you. "
            f"Tap to shop your size with fast, free US shipping today at us.meeeshop.com!"
        )
        try:
            gTTS(text=vo_text, lang="en", tld="us").save(vo_path)
            vo = AudioFileClip(vo_path)
            if vo.duration > total_secs:
                vo = vo.subclip(0, total_secs - 0.5)
            audio_clips.append(vo.set_start(0.5).volumex(1.15))
            logger.info(f"Synchronized voiceover generated ({vo.duration:.1f}s)")
        except Exception as e:
            logger.warning(f"gTTS voiceover failed: {e}")

        if audio_clips:
            video = video.set_audio(CompositeAudioClip(audio_clips))

        out_path = str(OUT_DIR / f"{handle[:30]}_{int(time.time())}.mp4")
        logger.info(f"Rendering multi-scene feature video → {out_path}")
        video.write_videofile(
            out_path, fps=FPS, codec="libx264", audio_codec="aac",
            temp_audiofile=os.path.join(tmp, "tmp_audio.m4a"),
            remove_temp=True, verbose=False, logger=None,
            ffmpeg_params=["-crf", "18", "-preset", "fast", "-b:a", "192k"],
        )

    video.close()
    size_mb = os.path.getsize(out_path) / 1_048_576
    logger.info(f"Rendered video: {os.path.basename(out_path)} ({size_mb:.1f} MB)")
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

    # Pick products for this run using category LRU rotation
    from pinterest_daily_v2 import select_next_product_lru
    used_indices = set()
    to_post = []
    for _ in range(min(MAX_PINS_PER_RUN, len(available))):
        s_idx = select_next_product_lru(available, used_indices, history)
        if s_idx is not None:
            used_indices.add(s_idx)
            to_post.append(available[s_idx])

    if not to_post:
        to_post = available[:MAX_PINS_PER_RUN]

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

        from pinterest_daily_v2 import get_product_main_category
        cat = get_product_main_category(product.get("title", ""), product.get("product_type", ""), str(product.get("tags", "")))
        if "category_last_used" not in history:
            history["category_last_used"] = {}
        history["category_last_used"][cat] = datetime.now(timezone.utc).isoformat()

        history["posts"].append({
            "product_id":      str(product.get("id", "")),
            "product_handle":  product.get("handle", ""),
            "product_title":   product["title"],
            "category":        cat,
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
