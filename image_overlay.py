"""
image_overlay.py — Pinterest pin image designer for MeeeShop.
Produces Kohl's-style pins: bold category label top, product photo center,
price badge, and solid CTA button bar at bottom. 1000x1500px (2:3 ratio).
Uses Pillow only — no extra deps beyond what's already installed.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# ── Pin canvas specs ────────────────────────────────────────────────────────
PIN_W = 1000
PIN_H = 1500
PIN_QUALITY = 95

# ── Brand palette ────────────────────────────────────────────────────────────
COLOR_BG        = (250, 248, 246)   # warm off-white
COLOR_TOP_BAR   = (30,  30,  30)    # near-black header bar
COLOR_CTA_BAR   = (30,  30,  30)    # matching CTA footer bar
COLOR_LABEL_TXT = (255, 255, 255)   # white on dark bars
COLOR_TITLE_TXT = (30,  30,  30)    # dark text on light bg
COLOR_PRICE_BG  = (220, 53,  69)    # red badge
COLOR_PRICE_TXT = (255, 255, 255)

# ── Layout proportions ───────────────────────────────────────────────────────
TOP_BAR_H   = int(PIN_H * 0.10)   # category label band
PHOTO_Y     = TOP_BAR_H
PHOTO_H     = int(PIN_H * 0.68)   # product photo area
INFO_Y      = PHOTO_Y + PHOTO_H   # title + price area
INFO_H      = int(PIN_H * 0.12)
CTA_Y       = INFO_Y + INFO_H
CTA_H       = PIN_H - CTA_Y       # CTA button bar fills the rest


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a font at the given size. Tries system paths then PIL default."""
    candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial Bold.ttf",
        "arial.ttf",
    ]
    candidates_reg = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "arial.ttf",
    ]
    candidates = candidates_bold if bold else candidates_reg
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # PIL bitmap default — better than crashing
    return ImageFont.load_default()


def _draw_rounded_rect(draw: ImageDraw.Draw, xy: Tuple, radius: int, fill):
    """Draw a rectangle with rounded corners."""
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2*radius, y0 + 2*radius], fill=fill)
    draw.ellipse([x1 - 2*radius, y0, x1, y0 + 2*radius], fill=fill)
    draw.ellipse([x0, y1 - 2*radius, x0 + 2*radius, y1], fill=fill)
    draw.ellipse([x1 - 2*radius, y1 - 2*radius, x1, y1], fill=fill)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit max_width pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _fit_image_to_box(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Scale image to fill box (cover), then center-crop."""
    src_w, src_h = img.size
    scale = max(box_w / src_w, box_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x = (new_w - box_w) // 2
    y = (new_h - box_h) // 2
    return img.crop((x, y, x + box_w, y + box_h))


def create_pin_image(
    product_image_path: str,
    title: str,
    category: str = "New Arrival",
    price: Optional[str] = None,
    cta: str = "Shop Now at MeeeShop.com",
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Create a Kohl's-style Pinterest pin image.

    Layout (top → bottom):
      ┌────────────────────────┐  TOP_BAR_H   dark bar: category label
      │  product photo         │  PHOTO_H     cover-fit, slight contrast boost
      │                        │
      │  title  [price badge]  │  INFO_H      white area: product name + price
      ├────────────────────────┤
      │  SHOP NOW AT ...       │  CTA_H       dark CTA footer bar
      └────────────────────────┘

    Args:
        product_image_path: Local path to product photo
        title: Product name
        category: Short label for top bar (e.g. "Trending: Dresses")
        price: Price string without $ (e.g. "49.99") — optional
        cta: Call-to-action text for the footer bar
        output_path: Where to save; auto-generated temp file if None

    Returns:
        Path to finished pin image, or None on failure
    """
    try:
        # ── Canvas ────────────────────────────────────────────────────────
        canvas = Image.new("RGB", (PIN_W, PIN_H), COLOR_BG)
        draw = ImageDraw.Draw(canvas)

        # ── Top bar (category label) ──────────────────────────────────────
        draw.rectangle([(0, 0), (PIN_W, TOP_BAR_H)], fill=COLOR_TOP_BAR)
        cat_font = _get_font(int(TOP_BAR_H * 0.40), bold=True)
        cat_text = category.upper()
        bbox = cat_font.getbbox(cat_text)
        cat_x = (PIN_W - (bbox[2] - bbox[0])) // 2
        cat_y = (TOP_BAR_H - (bbox[3] - bbox[1])) // 2
        draw.text((cat_x, cat_y), cat_text, fill=COLOR_LABEL_TXT, font=cat_font)

        # ── Product photo ─────────────────────────────────────────────────
        if Path(product_image_path).exists():
            img = Image.open(product_image_path).convert("RGB")
            # Slight contrast boost for Pinterest vibrancy
            img = ImageEnhance.Contrast(img).enhance(1.08)
            img = ImageEnhance.Color(img).enhance(1.05)
            img = _fit_image_to_box(img, PIN_W, PHOTO_H)
            canvas.paste(img, (0, PHOTO_Y))
        else:
            # Gray placeholder if image missing
            draw.rectangle([(0, PHOTO_Y), (PIN_W, PHOTO_Y + PHOTO_H)], fill=(200, 200, 200))
            logger.warning(f"Product image not found: {product_image_path}")

        # ── Info area (title + price badge) ───────────────────────────────
        draw.rectangle([(0, INFO_Y), (PIN_W, INFO_Y + INFO_H)], fill=COLOR_BG)

        margin = int(PIN_W * 0.05)
        title_font = _get_font(int(INFO_H * 0.30), bold=True)
        title_lines = _wrap_text(title, title_font, PIN_W - 2 * margin - (160 if price else 0))

        line_h = int(INFO_H * 0.33)
        for i, line in enumerate(title_lines[:2]):  # max 2 lines
            y = INFO_Y + int(INFO_H * 0.12) + i * line_h
            draw.text((margin, y), line, fill=COLOR_TITLE_TXT, font=title_font)

        # Price badge — red pill on the right side of info area
        if price:
            price_str = f"${price}"
            price_font = _get_font(int(INFO_H * 0.32), bold=True)
            pb = price_font.getbbox(price_str)
            pw = (pb[2] - pb[0]) + 28
            ph = (pb[3] - pb[1]) + 16
            px = PIN_W - margin - pw
            py = INFO_Y + (INFO_H - ph) // 2
            _draw_rounded_rect(draw, (px, py, px + pw, py + ph), radius=8, fill=COLOR_PRICE_BG)
            draw.text((px + 14, py + 8), price_str, fill=COLOR_PRICE_TXT, font=price_font)

        # ── CTA footer bar ────────────────────────────────────────────────
        draw.rectangle([(0, CTA_Y), (PIN_W, PIN_H)], fill=COLOR_CTA_BAR)
        cta_text = cta.upper()
        cta_margin = int(PIN_W * 0.04)
        max_cta_w = PIN_W - 2 * cta_margin
        cta_size = int(CTA_H * 0.28)
        cta_font = _get_font(cta_size, bold=True)
        # Auto-shrink until text fits
        while cta_size > 12:
            cb = cta_font.getbbox(cta_text)
            if (cb[2] - cb[0]) <= max_cta_w:
                break
            cta_size -= 2
            cta_font = _get_font(cta_size, bold=True)
        cb = cta_font.getbbox(cta_text)
        cta_x = (PIN_W - (cb[2] - cb[0])) // 2
        cta_y_pos = CTA_Y + (CTA_H - (cb[3] - cb[1])) // 2
        draw.text((cta_x, cta_y_pos), cta_text, fill=COLOR_LABEL_TXT, font=cta_font)

        # ── Save ──────────────────────────────────────────────────────────
        if not output_path:
            tmp = tempfile.mktemp(suffix=".jpg", prefix="pin_final_")
            output_path = tmp

        canvas.save(output_path, format="JPEG", quality=PIN_QUALITY, optimize=True)
        logger.info(f"Created overlay image: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to create pin image: {e}", exc_info=True)
        return None


# ── Public aliases used by pinterest_daily.py ───────────────────────────────

def add_text_overlay(
    image_path: str,
    title: str,
    cta: str = "Shop Now",
    price: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Backward-compatible wrapper called by pinterest_daily.py."""
    # Derive a short category label from the title
    title_lower = title.lower()
    if any(w in title_lower for w in ("dress", "gown", "midi", "maxi")):
        category = "Trending: Dresses"
    elif any(w in title_lower for w in ("top", "blouse", "shirt", "cami")):
        category = "Trending: Tops"
    elif any(w in title_lower for w in ("jeans", "denim", "pants", "legging")):
        category = "Trending: Bottoms"
    elif any(w in title_lower for w in ("jacket", "coat", "shacket", "blazer")):
        category = "Trending: Outerwear"
    elif any(w in title_lower for w in ("sweater", "cardigan", "knit")):
        category = "Trending: Sweaters"
    elif any(w in title_lower for w in ("skirt",)):
        category = "Trending: Skirts"
    elif any(w in title_lower for w in ("bag", "backpack", "purse", "tote")):
        category = "Trending: Bags"
    else:
        category = "New Arrival"

    return create_pin_image(
        product_image_path=image_path,
        title=title,
        category=category,
        price=price,
        cta=f"{cta} at us.MeeeShop.com",
        output_path=output_path,
    )


def optimize_image_for_pinterest(image_path: str, output_path: Optional[str] = None) -> Optional[str]:
    """Backward-compatible: resize image to PIN_W x PIN_H canvas."""
    try:
        img = Image.open(image_path).convert("RGB")
        img = _fit_image_to_box(img, PIN_W, PIN_H)
        if not output_path:
            output_path = str(Path(image_path).parent / "pin_optimized.jpg")
        img.save(output_path, format="JPEG", quality=PIN_QUALITY, optimize=True)
        logger.info(f"Optimized image: {PIN_W}x{PIN_H} → {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to optimize image: {e}")
        return None


def create_video_pin_thumbnail(
    title: str,
    description: str,
    image_width: int = PIN_W,
    image_height: int = PIN_H,
    output_path: str = "video_thumbnail.jpg",
) -> Optional[str]:
    """Create a simple video pin thumbnail (gradient bg + text)."""
    try:
        canvas = Image.new("RGB", (image_width, image_height), (30, 30, 30))
        draw = ImageDraw.Draw(canvas)
        for y in range(image_height):
            t = y / image_height
            r = int(30 + 20 * t)
            draw.line([(0, y), (image_width, y)], fill=(r, 30, 50))

        # VIDEO badge
        badge_font = _get_font(int(image_width * 0.08), bold=True)
        draw.rectangle([(40, 60), (240, 120)], fill=(220, 53, 69))
        draw.text((55, 68), "▶ VIDEO", fill=(255, 255, 255), font=badge_font)

        # Title
        title_font = _get_font(int(image_width * 0.065), bold=True)
        margin = int(image_width * 0.07)
        title_lines = _wrap_text(title[:80], title_font, image_width - 2 * margin)
        for i, line in enumerate(title_lines[:3]):
            draw.text((margin, int(image_height * 0.35) + i * int(image_width * 0.09)),
                      line, fill=(255, 255, 255), font=title_font)

        canvas.save(output_path, format="JPEG", quality=PIN_QUALITY, optimize=True)
        logger.info(f"Created video thumbnail: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to create video thumbnail: {e}")
        return None
