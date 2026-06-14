"""
image_overlay.py — Pinterest pin image designer for MeeeShop.
5 rotating Kohl's-style templates, selected by product ID hash so each
product always gets the same layout but variety appears across the feed.

Templates modelled on Kohl's Pinterest pins:
  A — Dark header + full photo + dark info strip + red CTA bar
  B — Full-bleed photo with gradient overlay; text bottom-left; red pill CTA
  C — Light bg, large italic category text top-left, photo right-aligned, price bottom
  D — Solid accent-color top half + photo bottom half (split)
  E — Full photo + bold text box floating bottom-center + CTA strip
"""

import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageEnhance

logger = logging.getLogger(__name__)

PIN_W = 1000
PIN_H = 1500
PIN_QUALITY = 95

CTA_TEXT = "SHOP NOW AT US.MEEESHOP.COM"

# Palette
BLACK      = (20,  20,  20)
WHITE      = (255, 255, 255)
RED        = (220, 53,  69)
WARM_WHITE = (250, 248, 244)
DARK_GREY  = (40,  40,  40)
MID_GREY   = (90,  90,  90)
CORAL      = (232, 93,  78)
NAVY       = (22,  43,  77)
SAGE       = (88,  120, 90)
BLUSH      = (230, 185, 175)


# ── Font helpers ─────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "arial.ttf",
        ] if bold else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "arial.ttf",
        ]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int) -> list:
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        try:
            w = font.getbbox(test)[2] - font.getbbox(test)[0]
        except Exception:
            w = len(test) * 10
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _fit_image(img: Image.Image, w: int, h: int) -> Image.Image:
    """Cover-fit: scale to fill box then center-crop."""
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))


def _draw_rounded_rect(draw, xy: Tuple, r: int, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)
    for ex, ey in [(x0, y0), (x1 - 2*r, y0), (x0, y1 - 2*r), (x1 - 2*r, y1 - 2*r)]:
        draw.ellipse([ex, ey, ex + 2*r, ey + 2*r], fill=fill)


def _fit_text(text: str, bold: bool, max_w: int, start_size: int, min_size: int = 14) -> Tuple:
    """Return (font, text) shrunk until text fits max_w."""
    size = start_size
    while size >= min_size:
        f = _get_font(size, bold)
        try:
            tw = f.getbbox(text)[2] - f.getbbox(text)[0]
        except Exception:
            tw = len(text) * size // 2
        if tw <= max_w:
            return f, text
        size -= 2
    return _get_font(min_size, bold), text


def _draw_cta_bar(canvas: Image.Image, draw: ImageDraw.Draw,
                  y: int, h: int, bg: tuple, fg: tuple):
    """Draw the CTA footer bar with auto-fit text."""
    draw.rectangle([(0, y), (PIN_W, y + h)], fill=bg)
    margin = int(PIN_W * 0.05)
    font, text = _fit_text(CTA_TEXT, bold=True, max_w=PIN_W - 2 * margin,
                           start_size=int(h * 0.38))
    try:
        tb = font.getbbox(text)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
    except Exception:
        tw, th = PIN_W - 2 * margin, h // 2
    draw.text(((PIN_W - tw) // 2, y + (h - th) // 2), text, fill=fg, font=font)


def _boost(img: Image.Image) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(1.06)
    return img


# ── Template A ───────────────────────────────────────────────────────────────
# Dark header bar | full photo | dark info strip | red CTA bar
# Like: Kohl's "Trending: Polo Shirts" layout
def _template_a(draw, canvas, photo, title, category, price):
    TOP_H  = int(PIN_H * 0.10)
    CTA_H  = int(PIN_H * 0.10)
    INFO_H = int(PIN_H * 0.13)
    PHOTO_H = PIN_H - TOP_H - INFO_H - CTA_H

    # Dark top bar — category
    draw.rectangle([(0, 0), (PIN_W, TOP_H)], fill=BLACK)
    cat_f, _ = _fit_text(category.upper(), True, PIN_W - 80, int(TOP_H * 0.45))
    cb = cat_f.getbbox(category.upper())
    draw.text(((PIN_W - (cb[2]-cb[0])) // 2, (TOP_H - (cb[3]-cb[1])) // 2),
              category.upper(), fill=WHITE, font=cat_f)

    # Photo
    p = _boost(_fit_image(photo, PIN_W, PHOTO_H))
    canvas.paste(p, (0, TOP_H))

    # Dark info strip
    info_y = TOP_H + PHOTO_H
    draw.rectangle([(0, info_y), (PIN_W, info_y + INFO_H)], fill=DARK_GREY)
    margin = int(PIN_W * 0.05)
    tf = _get_font(int(INFO_H * 0.28), bold=True)
    lines = _wrap_text(title, tf, PIN_W - 2*margin - (180 if price else 0))
    lh = int(INFO_H * 0.33)
    for i, line in enumerate(lines[:2]):
        draw.text((margin, info_y + int(INFO_H * 0.10) + i * lh), line, fill=WHITE, font=tf)

    if price:
        pf = _get_font(int(INFO_H * 0.30), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+28, pb[3]-pb[1]+16
        px = PIN_W - margin - pw
        py = info_y + (INFO_H - ph) // 2
        _draw_rounded_rect(draw, (px, py, px+pw, py+ph), 8, WHITE)
        draw.text((px+14, py+8), ps, fill=BLACK, font=pf)

    # Red CTA
    _draw_cta_bar(canvas, draw, info_y + INFO_H, CTA_H, RED, WHITE)


# ── Template B ───────────────────────────────────────────────────────────────
# Full-bleed photo with dark gradient overlay at bottom; text over photo;
# white pill price badge; red CTA strip.
# Like: Kohl's "Graduation Dresses" / "Casual Work Outfits" layout
def _template_b(draw, canvas, photo, title, category, price):
    CTA_H = int(PIN_H * 0.10)
    PHOTO_H = PIN_H - CTA_H

    # Full photo
    p = _boost(_fit_image(photo, PIN_W, PHOTO_H))
    canvas.paste(p, (0, 0))

    # Dark gradient over bottom 40% of photo
    grad_h = int(PHOTO_H * 0.42)
    grad_start = PHOTO_H - grad_h
    overlay = Image.new("RGBA", (PIN_W, PHOTO_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(grad_h):
        alpha = int(200 * (y / grad_h))
        od.rectangle([(0, grad_start + y), (PIN_W, grad_start + y + 1)],
                     fill=(0, 0, 0, alpha))
    canvas.paste(Image.alpha_composite(p.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(canvas)

    # Category label — italic style, small, upper-left of gradient zone
    margin = int(PIN_W * 0.06)
    cf = _get_font(int(PIN_H * 0.030), bold=False)
    draw.text((margin, grad_start + int(grad_h * 0.18)), category.upper(),
              fill=(220, 220, 220), font=cf)

    # Title — large bold
    tf_size = int(PIN_H * 0.062)
    tf = _get_font(tf_size, bold=True)
    lines = _wrap_text(title, tf, PIN_W - 2*margin - (200 if price else 0))
    title_y = grad_start + int(grad_h * 0.30)
    lh = int(tf_size * 1.25)
    for i, line in enumerate(lines[:2]):
        draw.text((margin, title_y + i * lh), line, fill=WHITE, font=tf)

    # Price badge — white pill, bottom-right
    if price:
        pf = _get_font(int(PIN_H * 0.040), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+32, pb[3]-pb[1]+18
        px = PIN_W - margin - pw
        py = PHOTO_H - ph - int(PIN_H * 0.04)
        _draw_rounded_rect(draw, (px, py, px+pw, py+ph), 10, RED)
        draw.text((px+16, py+9), ps, fill=WHITE, font=pf)

    # Red CTA strip
    _draw_cta_bar(canvas, draw, PHOTO_H, CTA_H, RED, WHITE)


# ── Template C ───────────────────────────────────────────────────────────────
# Warm white bg; large bold category text top; photo centered with padding;
# price bottom-left; CTA bar navy.
# Like: Kohl's "Summer looks for the little ones" / flat-lay style
def _template_c(draw, canvas, photo, title, category, price):
    HEADER_H = int(PIN_H * 0.18)
    CTA_H    = int(PIN_H * 0.10)
    FOOTER_H = int(PIN_H * 0.12)
    PHOTO_H  = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD      = int(PIN_W * 0.04)

    draw.rectangle([(0, 0), (PIN_W, PIN_H)], fill=WARM_WHITE)

    # Large category text — two-line split if contains ":"
    parts = category.split(":", 1) if ":" in category else [category, ""]
    line1 = parts[0].strip()
    line2 = parts[1].strip() if parts[1] else ""
    f1 = _get_font(int(HEADER_H * 0.32), bold=False)
    f2 = _get_font(int(HEADER_H * 0.42), bold=True)
    margin = int(PIN_W * 0.06)
    b1 = f1.getbbox(line1)
    draw.text((margin, int(HEADER_H * 0.12)), line1, fill=BLACK, font=f1)
    if line2:
        draw.text((margin, int(HEADER_H * 0.12) + (b1[3]-b1[1]) + 4),
                  line2.upper(), fill=BLACK, font=f2)
    else:
        draw.text((margin, int(HEADER_H * 0.30)), line1.upper(), fill=BLACK, font=f2)

    # Photo with slight shadow effect (paste on slightly offset dark rect)
    p = _boost(_fit_image(photo, PIN_W - PAD*2, PHOTO_H - PAD*2))
    shadow = Image.new("RGB", (PIN_W - PAD*2 + 8, PHOTO_H - PAD*2 + 8), (180, 180, 180))
    canvas.paste(shadow, (PAD + 4, HEADER_H + PAD + 4))
    canvas.paste(p, (PAD, HEADER_H + PAD))
    draw = ImageDraw.Draw(canvas)

    # Footer: title left, price badge right
    footer_y = HEADER_H + PHOTO_H
    draw.rectangle([(0, footer_y), (PIN_W, footer_y + FOOTER_H)], fill=WARM_WHITE)
    tf = _get_font(int(FOOTER_H * 0.30), bold=True)
    lines = _wrap_text(title, tf, PIN_W - 2*margin - (160 if price else 0))
    lh = int(FOOTER_H * 0.34)
    for i, line in enumerate(lines[:2]):
        draw.text((margin, footer_y + int(FOOTER_H * 0.10) + i*lh), line, fill=BLACK, font=tf)

    if price:
        pf = _get_font(int(FOOTER_H * 0.32), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+28, pb[3]-pb[1]+16
        px = PIN_W - margin - pw
        py = footer_y + (FOOTER_H - ph) // 2
        _draw_rounded_rect(draw, (px, py, px+pw, py+ph), 8, RED)
        draw.text((px+14, py+8), ps, fill=WHITE, font=pf)

    # Navy CTA
    _draw_cta_bar(canvas, draw, footer_y + FOOTER_H, CTA_H, NAVY, WHITE)


# ── Template D ───────────────────────────────────────────────────────────────
# Solid accent-color top band with big headline; photo fills lower 2/3;
# price badge overlaps the photo/band boundary; black CTA strip.
# Like: Kohl's "Playful two-pieces" / "Swimsuits for the whole family"
def _template_d(draw, canvas, photo, title, category, price, accent=CORAL):
    BAND_H  = int(PIN_H * 0.22)
    CTA_H   = int(PIN_H * 0.10)
    PHOTO_H = PIN_H - BAND_H - CTA_H

    # Accent top band
    draw.rectangle([(0, 0), (PIN_W, BAND_H)], fill=accent)

    # Category in white — smaller top line
    margin = int(PIN_W * 0.06)
    cf = _get_font(int(BAND_H * 0.22), bold=False)
    draw.text((margin, int(BAND_H * 0.10)), category.upper(), fill=WHITE, font=cf)

    # Title in white — big bold
    tf = _get_font(int(BAND_H * 0.32), bold=True)
    lines = _wrap_text(title, tf, PIN_W - 2*margin)
    lh = int(BAND_H * 0.36)
    title_start = int(BAND_H * 0.35)
    for i, line in enumerate(lines[:2]):
        draw.text((margin, title_start + i*lh), line, fill=WHITE, font=tf)

    # Photo
    p = _boost(_fit_image(photo, PIN_W, PHOTO_H))
    canvas.paste(p, (0, BAND_H))
    draw = ImageDraw.Draw(canvas)

    # Price badge overlapping band/photo border
    if price:
        pf = _get_font(int(PIN_H * 0.038), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+36, pb[3]-pb[1]+20
        px = PIN_W - margin - pw
        py = BAND_H - ph // 2
        _draw_rounded_rect(draw, (px, py, px+pw, py+ph), 10, WHITE)
        draw.text((px+18, py+10), ps, fill=BLACK, font=pf)

    # Black CTA
    _draw_cta_bar(canvas, draw, BAND_H + PHOTO_H, CTA_H, BLACK, WHITE)


# ── Template E ───────────────────────────────────────────────────────────────
# Full-bleed photo; floating semi-transparent dark text box center-bottom;
# red CTA strip.
# Like: Kohl's "Cute and colorful summer styles" layout
def _template_e(draw, canvas, photo, title, category, price):
    CTA_H   = int(PIN_H * 0.10)
    PHOTO_H = PIN_H - CTA_H

    # Full photo
    p = _boost(_fit_image(photo, PIN_W, PHOTO_H))
    canvas.paste(p, (0, 0))
    draw = ImageDraw.Draw(canvas)

    # Floating text box — semi-transparent, bottom center
    box_w = int(PIN_W * 0.88)
    box_h = int(PIN_H * 0.22)
    box_x = (PIN_W - box_w) // 2
    box_y = PHOTO_H - box_h - int(PIN_H * 0.04)

    # Semi-transparent overlay box
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    _draw_rounded_rect(od, (box_x, box_y, box_x + box_w, box_y + box_h), 16,
                       (20, 20, 20, 210))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"),
                 (0, 0))
    draw = ImageDraw.Draw(canvas)

    # Category small label inside box
    inner_margin = int(box_w * 0.06)
    cf = _get_font(int(box_h * 0.17), bold=False)
    draw.text((box_x + inner_margin, box_y + int(box_h * 0.08)),
              category.upper(), fill=(200, 200, 200), font=cf)

    # Title bold
    tf = _get_font(int(box_h * 0.26), bold=True)
    lines = _wrap_text(title, tf, box_w - 2*inner_margin - (160 if price else 0))
    lh = int(box_h * 0.30)
    for i, line in enumerate(lines[:2]):
        draw.text((box_x + inner_margin, box_y + int(box_h * 0.36) + i*lh),
                  line, fill=WHITE, font=tf)

    # Price badge inside box, right side
    if price:
        pf = _get_font(int(box_h * 0.25), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+28, pb[3]-pb[1]+14
        px = box_x + box_w - inner_margin - pw
        py = box_y + box_h - ph - int(box_h * 0.10)
        _draw_rounded_rect(draw, (px, py, px+pw, py+ph), 8, RED)
        draw.text((px+14, py+7), ps, fill=WHITE, font=pf)

    # Red CTA strip
    _draw_cta_bar(canvas, draw, PHOTO_H, CTA_H, RED, WHITE)


# ── Accent colour cycle for template D ───────────────────────────────────────
_ACCENTS = [CORAL, NAVY, SAGE, (180, 100, 160), (60, 130, 160)]


# ── Main entry ───────────────────────────────────────────────────────────────

def create_pin_image(
    product_image_path: str,
    title: str,
    category: str = "New Arrival",
    price: Optional[str] = None,
    cta: str = "Shop Now at us.MeeeShop.com",
    output_path: Optional[str] = None,
    template_index: Optional[int] = None,
) -> Optional[str]:
    """
    Create a Pinterest pin using one of 5 rotating Kohl's-style templates.
    template_index 0-4 selects the template; None picks by hashing the title.
    """
    try:
        if template_index is None:
            template_index = int(hashlib.md5(title.encode()).hexdigest(), 16) % 5

        canvas = Image.new("RGB", (PIN_W, PIN_H), WARM_WHITE)
        draw = ImageDraw.Draw(canvas)

        if Path(product_image_path).exists():
            photo = Image.open(product_image_path).convert("RGB")
        else:
            photo = Image.new("RGB", (PIN_W, PIN_H), (200, 200, 200))
            logger.warning(f"Product image not found: {product_image_path}")

        logger.info(f"Using pin template {template_index} for: {title[:40]}")

        if template_index == 0:
            _template_a(draw, canvas, photo, title, category, price)
        elif template_index == 1:
            _template_b(draw, canvas, photo, title, category, price)
        elif template_index == 2:
            _template_c(draw, canvas, photo, title, category, price)
        elif template_index == 3:
            accent = _ACCENTS[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(_ACCENTS)]
            _template_d(draw, canvas, photo, title, category, price, accent=accent)
        else:
            _template_e(draw, canvas, photo, title, category, price)

        if not output_path:
            output_path = tempfile.mktemp(suffix=".jpg", prefix="pin_final_")

        canvas.save(output_path, format="JPEG", quality=PIN_QUALITY, optimize=True)
        logger.info(f"Created overlay image: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to create pin image: {e}", exc_info=True)
        return None


# ── Public aliases ────────────────────────────────────────────────────────────

def add_text_overlay(
    image_path: str,
    title: str,
    cta: str = "Shop Now",
    price: Optional[str] = None,
    output_path: Optional[str] = None,
    template_index: Optional[int] = None,
) -> Optional[str]:
    """Called by pinterest_daily.py — derives category label then delegates."""
    import re
    tl = title.lower()

    def match_word_or_sub(keywords, boundary_keys={"top", "flat"}):
        for kw in keywords:
            if kw in boundary_keys:
                if kw == "top":
                    if re.search(r'\btops?(?!-handle|-loading|-heavy)\b', tl):
                        return True
                else:
                    if re.search(r'\b' + re.escape(kw) + r's?\b', tl):
                        return True
            else:
                if kw in tl:
                    return True
        return False

    if match_word_or_sub(("bag", "backpack", "purse", "tote", "handbag", "crossbody", "clutch", "satchel", "wallet", "pouch", "duffel", "hobo")):
        category = "Trending: Bags"
    elif match_word_or_sub(("dress", "gown", "midi", "maxi", "mini")):
        category = "Trending: Dresses"
    elif match_word_or_sub(("top", "blouse", "shirt", "cami", "tank")):
        category = "Trending: Tops"
    elif match_word_or_sub(("jeans", "denim", "pants", "legging")):
        category = "Trending: Bottoms"
    elif match_word_or_sub(("jacket", "coat", "shacket", "blazer")):
        category = "Trending: Outerwear"
    elif match_word_or_sub(("sweater", "cardigan", "knit", "pullover")):
        category = "Trending: Sweaters"
    elif "skirt" in tl:
        category = "Trending: Skirts"
    else:
        category = "New Arrival"

    return create_pin_image(
        product_image_path=image_path,
        title=title,
        category=category,
        price=price,
        output_path=output_path,
        template_index=template_index,
    )


def optimize_image_for_pinterest(image_path: str, output_path: Optional[str] = None) -> Optional[str]:
    try:
        img = Image.open(image_path).convert("RGB")
        img = _fit_image(img, PIN_W, PIN_H)
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
    try:
        canvas = Image.new("RGB", (image_width, image_height), (30, 30, 30))
        draw = ImageDraw.Draw(canvas)
        for y in range(image_height):
            t = y / image_height
            draw.line([(0, y), (image_width, y)], fill=(int(30 + 20*t), 30, 50))
        badge_font = _get_font(int(image_width * 0.07), bold=True)
        draw.rectangle([(40, 60), (280, 125)], fill=RED)
        draw.text((58, 70), "▶ VIDEO", fill=WHITE, font=badge_font)
        tf = _get_font(int(image_width * 0.065), bold=True)
        margin = int(image_width * 0.07)
        for i, line in enumerate(_wrap_text(title[:80], tf, image_width - 2*margin)[:3]):
            draw.text((margin, int(image_height * 0.35) + i * int(image_width * 0.09)),
                      line, fill=WHITE, font=tf)
        canvas.save(output_path, format="JPEG", quality=PIN_QUALITY, optimize=True)
        logger.info(f"Created video thumbnail: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to create video thumbnail: {e}")
        return None
