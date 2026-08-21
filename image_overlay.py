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
import os
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple, List



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

_ACCENTS = [
    (238, 242, 247), # Slate blue tint
    (247, 243, 238), # Peach tint
    (240, 247, 242), # Mint tint
    (247, 238, 242), # Blush tint
    (238, 238, 247), # Lavender tint
]
CORAL      = (232, 93,  78)
NAVY       = (22,  43,  77)
SAGE       = (88,  120, 90)
BLUSH      = (230, 185, 175)


def _get_font(size: int, bold: bool = False, serif: bool = False, italic: bool = False, script: bool = False) -> ImageFont.FreeTypeFont:
    if script:
        candidates = [
            "C:/Windows/Fonts/segoesc.ttf",
            "C:/Windows/Fonts/georgiai.ttf",
            "C:/Windows/Fonts/ariali.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        ]
    elif serif:
        if italic and bold:
            candidates = [
                "C:/Windows/Fonts/georgiaz.ttf",
                "C:/Windows/Fonts/timesbi.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
            ]
        elif italic:
            candidates = [
                "C:/Windows/Fonts/georgiai.ttf",
                "C:/Windows/Fonts/timesi.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
            ]
        elif bold:
            candidates = [
                "C:/Windows/Fonts/georgiab.ttf",
                "C:/Windows/Fonts/timesbd.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            ]
        else:
            candidates = [
                "C:/Windows/Fonts/georgia.ttf",
                "C:/Windows/Fonts/times.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            ]
    else:
        candidates = (
            [
                "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
                "arial.ttf",
            ] if bold else [
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
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
    """
    Cover-fit with top-weighted smart crop to preserve faces, necklines, and full outfit framing.
    Avoids cutting off model heads or collar details on tall apparel.
    """
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)

    # Top-weighted cropping for fashion: position crop slightly higher (20%) so model face/head is preserved
    x = (nw - w) // 2
    if nh > h:
        y = int((nh - h) * 0.18)
        y = max(0, min(y, nh - h))
    else:
        y = 0
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
    """
    Hero Image Polish:
    Enhances contrast (+10%), color vibrancy (+8%), and sharpness (+25%)
    so fabric textures, lace/knit patterns, and garment details pop on mobile screens.
    """
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageEnhance.Color(img).enhance(1.08)
    img = ImageEnhance.Sharpness(img).enhance(1.25)
    return img


# ── 2026 Luxury Contemporary Boutique Pin Engine ───────────────────────────
# Strict 2:3 vertical (1000x1500 px) Pinterest standard layout.
# Follows modern luxury boutique aesthetics (Revolve, Aritzia, Zara, Anthropologie):
#   - Zero solid black/red blocks covering the photo
#   - Smooth bottom vertical gradient vignette for natural contrast
#   - Editorial letter-spaced brand hook (M E E E S H O P • E D I T)
#   - Crisp pure white typography with subtle drop-shadows
#   - Frosted glass trust pill (Top-Right)
#   - Elegant cream pill CTA button (SHOP THE LOOK → US.MEEESHOP.COM)
def _render_direct_pin(
    draw: ImageDraw.Draw,
    canvas: Image.Image,
    photo: Image.Image,
    title: str,
    category: str = "New Arrival",
    price: Optional[str] = None,
    cta: str = "SHOP NOW AT US.MEEESHOP.COM",
    layout: str = "bottom_floating",
    trust_badge: Optional[str] = "FREE US SHIPPING",
):
    p = _boost(_fit_image(photo, PIN_W, PIN_H))
    canvas.paste(p, (0, 0))

    # Create an RGBA overlay for smooth gradient vignette and frosted elements
    overlay = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    # 1. Smooth Bottom Vertical Gradient Vignette (y=1080 to 1500)
    # Starts at y=1080, smoothly eases to rich dark (alpha=205) at bottom (y=1500)
    # Guarantees 100% mobile readability for bold white titles without needing to zoom in!
    vignette_start = 1080
    vignette_height = PIN_H - vignette_start
    for i in range(vignette_height):
        progress = i / float(vignette_height)
        alpha = int(210 * (progress ** 1.35))
        ov_draw.line([(0, vignette_start + i), (PIN_W, vignette_start + i)], fill=(10, 10, 14, alpha))

    # Also a subtle top gradient (y=0 to 130) for the top badge
    for i in range(130):
        progress = 1.0 - (i / 130.0)
        alpha = int(80 * (progress ** 1.5))
        ov_draw.line([(0, i), (PIN_W, i)], fill=(10, 10, 14, alpha))

    CREAM_WHITE    = (255, 255, 255, 255)
    CHAMPAGNE_GOLD = (255, 230, 130, 255)
    WARM_OAT       = (255, 245, 225, 255)
    FROSTED_GLASS  = (15, 15, 20, 205)       # 80% opacity sleek frosted dark glass
    SHADOW_DARK    = (5, 5, 8, 250)

    def draw_bold_shadowed_text(d, pos, text, font, fill=CREAM_WHITE, anchor=None):
        x, y = pos
        # 3px 16-direction bold contour shadow for crystal-clear mobile contrast
        offsets = [
            (-3, 0), (3, 0), (0, -3), (0, 3),
            (-3, -3), (3, 3), (-3, 3), (3, -3),
            (-2, -2), (2, 2), (-2, 2), (2, -2),
            (-2, 0), (2, 0), (0, -2), (0, 2),
            (-1, -1), (1, 1), (-1, 1), (1, -1)
        ]
        for dx, dy in offsets:
            if anchor:
                d.text((x + dx, y + dy), text, fill=SHADOW_DARK, font=font, anchor=anchor)
            else:
                d.text((x + dx, y + dy), text, fill=SHADOW_DARK, font=font)
        if anchor:
            d.text((x, y), text, fill=fill, font=font, anchor=anchor)
        else:
            d.text((x, y), text, fill=fill, font=font)

    # 2. Top-Right Frosted Glass Trust Badge (y=45)
    if trust_badge:
        tb_text = f"★  {trust_badge.upper()}"
        tb_font = _get_font(30, bold=True)
        tb_box = tb_font.getbbox(tb_text)
        tb_w = tb_box[2] - tb_box[0]
        tb_h = tb_box[3] - tb_box[1]

        pad_x, pad_y = 24, 12
        pill_w = tb_w + 2 * pad_x
        pill_h = tb_h + 2 * pad_y
        pill_x = PIN_W - pill_w - 45
        pill_y = 45

        # Frosted glass pill with subtle border
        _draw_rounded_rect(ov_draw, (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h), r=pill_h // 2, fill=FROSTED_GLASS)
        ov_draw.text((pill_x + pad_x, pill_y + pad_y - 2), tb_text, fill=CREAM_WHITE, font=tb_font)

    # 3. Clean Title & Category Formatting
    clean_title = (title or "").strip()
    for leak in ["we need", "create a", "product:", "type:"]:
        if leak in clean_title.lower():
            clean_title = "Trending Boutique Style"
            break

    # 4. Bottom High-Impact Typography Zone (y=1160 to y=1470)
    # Line 1: Bold Letter-spaced Brand Hook (26px)
    hook_text = "M E E E S H O P  •  N E W  A R R I V A L S"
    hook_font = _get_font(25, bold=True)
    draw_bold_shadowed_text(ov_draw, (PIN_W // 2, 1165), hook_text, hook_font, fill=CHAMPAGNE_GOLD, anchor="mt")

    # Line 2: Product Headline (52px ULTRA BOLD Modern Sans — Instantly readable on mobile)
    title_font = _get_font(50, bold=True, serif=False)
    title_lines = _wrap_text(clean_title.upper(), title_font, max_width=PIN_W - 100)
    display_title = title_lines[0] if title_lines else clean_title.upper()
    if len(title_lines) > 1 and len(display_title) > 28:
        display_title = display_title[:26] + "..."
    draw_bold_shadowed_text(ov_draw, (PIN_W // 2, 1215), display_title, title_font, fill=CREAM_WHITE, anchor="mt")

    # Line 3: Price & Guarantee (34px BOLD)
    price_str = f"${float(str(price).replace('$', '')):.2f}" if price and any(c.isdigit() for c in str(price)) else ""
    if price_str:
        sub_text = f"{price_str}   •   FREE US SHIPPING   •   7-DAY RETURNS"
    else:
        sub_text = "FREE US SHIPPING   •   TRUE-TO-SIZE FIT"
    sub_font = _get_font(32, bold=True)
    draw_bold_shadowed_text(ov_draw, (PIN_W // 2, 1295), sub_text, sub_font, fill=WARM_OAT, anchor="mt")

    # Line 4: Large High-Converting CTA Button (y=1365, Height=72px, Font=28px BOLD)
    cta_btn_w = 640
    cta_btn_h = 72
    cta_btn_x = (PIN_W - cta_btn_w) // 2
    cta_btn_y = 1365

    # Crisp pure white rounded pill button with bold charcoal text
    _draw_rounded_rect(ov_draw, (cta_btn_x, cta_btn_y, cta_btn_x + cta_btn_w, cta_btn_y + cta_btn_h), r=cta_btn_h // 2, fill=(255, 255, 255, 250))
    cta_font = _get_font(28, bold=True)
    ov_draw.text((PIN_W // 2, cta_btn_y + 19), "SHOP THE LOOK  →  US.MEEESHOP.COM", fill=(15, 15, 20, 255), font=cta_font, anchor="mt")

    # Merge RGBA overlay onto canvas
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def _template_a(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_b(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_c(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_d(draw, canvas, photo, title, category, price, accent=None):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_e(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_f(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_g(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_h(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_i(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_j(draw, canvas, photo, title, category, price=None, cta="Shop Now"):
    _render_direct_pin(draw, canvas, photo, title, category, price, cta, layout="bottom_floating")

def _template_k(draw, canvas, photo, photo2, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_l(draw, canvas, photo, photo2, photo3, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_m(draw, canvas, photo, title, category, price):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating")

def _template_n(draw, canvas, photo, title, category, price, cta="Shop Now"):
    _render_direct_pin(draw, canvas, photo, title, category, price, cta, layout="bottom_floating")

def _template_o(draw, canvas, photo, photo2, photo3, photo4, title, category, price, trust_badge=None):
    _render_direct_pin(draw, canvas, photo, title, category, price, layout="bottom_floating", trust_badge=trust_badge)

def _template_p(draw, canvas, photo, title, category, price, cta="Shop Now"):
    _render_direct_pin(draw, canvas, photo, title, category, price, cta, layout="bottom_floating")

def _template_q(draw, canvas, photo, title, category, price, cta="SHOP NOW AT US.MEEESHOP.COM"):
    _render_direct_pin(draw, canvas, photo, title, category, price, cta, layout="bottom_floating")





def _prepare_photo_for_style(
    photo: Image.Image,
    photo2: Optional[Image.Image],
    photo3: Optional[Image.Image],
    target_w: int,
    target_h: int,
    style: str,
) -> Image.Image:
    """
    Prepare product photo into target_w x target_h based on image_style ('hero', 'collage', 'card').
    Renders all 3 image styles dynamically for ANY template!
    """
    if style == "collage":
        composite = Image.new("RGB", (target_w, target_h), (255, 255, 255))
        gap = 4
        left_w = int(target_w * 0.58)
        right_w = target_w - left_w - gap
        right_h = (target_h - gap) // 2

        p_hero = _fit_image(photo, left_w, target_h)
        composite.paste(p_hero, (0, 0))

        if photo2 is not None:
            sub1 = photo2
        else:
            pw, ph = photo.size
            cw, ch = int(pw * 0.65), int(ph * 0.45)
            cx, cy = (pw - cw) // 2, int(ph * 0.08)
            sub1 = photo.crop((cx, cy, cx + cw, cy + ch))

        p_focus1 = _fit_image(sub1, right_w, right_h)
        composite.paste(p_focus1, (left_w + gap, 0))

        if photo3 is not None:
            sub2 = photo3
        elif photo2 is not None:
            sub2 = photo2
        else:
            pw, ph = photo.size
            cw, ch = int(pw * 0.65), int(ph * 0.45)
            cx, cy = (pw - cw) // 2, int(ph * 0.48)
            sub2 = photo.crop((cx, cy, cx + cw, cy + ch))

        p_focus2 = _fit_image(sub2, right_w, target_h - right_h - gap)
        composite.paste(p_focus2, (left_w + gap, right_h + gap))

        return _boost(composite)

    elif style == "card":
        return _boost(_fit_image(photo, target_w, target_h))

    else:
        return _boost(_fit_image(photo, target_w, target_h))


def _draw_trust_badge_pill(draw: ImageDraw.Draw, canvas: Image.Image, badge_text: str, y_top: int = 50, x_right: int = 50, bg_color=None, fg_color=WARM_WHITE):
    """
    Draw floating plain white/cream text directly on product image with ZERO background colors, cards, or pills.
    """
    bf = _get_font(36, bold=True)
    full_text = f"★  {badge_text}"
    bb = bf.getbbox(full_text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    px = PIN_W - x_right - tw
    py = y_top

    # 3px 16-direction ultra-bold contour outline for high contrast
    offsets = [
        (-3,0), (3,0), (0,-3), (0,3),
        (-3,-3), (3,3), (-3,3), (3,-3),
        (-2,-2), (2,2), (-2,2), (2,-2),
        (-2,0), (2,0), (0,-2), (0,2),
        (-1,-1), (1,1), (-1,1), (1,-1)
    ]
    for dx, dy in offsets:
        draw.text((px + dx, py + dy), full_text, fill=(15, 15, 15), font=bf)
    
    # Pure warm cream font directly on photo
    draw.text((px, py), full_text, fill=WARM_WHITE, font=bf)


# ── Main entry ───────────────────────────────────────────────────────────────

def create_pin_image(
    product_image_path: str,
    title: str,
    category: str = "New Arrival",
    price: Optional[str] = None,
    cta: str = "Shop Now at us.MeeeShop.com",
    output_path: Optional[str] = None,
    template_index: Optional[int] = None,
    additional_image_paths: Optional[List[str]] = None,
    board_name: str = "",
    image_style: str = "hero",
) -> Optional[str]:
    """
    Create a Pinterest pin using dynamic template matching and image_style framing
    ('hero', 'collage', 'card').
    """
    try:
        ecommerce_templates = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14]
        
        # Smart template matching based on board name
        b_lower = board_name.lower()
        if template_index is None:
            if "poetcore" in b_lower:
                template_index = 5
            elif "vamp" in b_lower or "romantic" in b_lower:
                template_index = 7
            elif "gummy" in b_lower or "nostalgia" in b_lower:
                template_index = 8
            elif "athlete" in b_lower or "off-duty" in b_lower:
                template_index = 10
            elif "blog" in b_lower:
                template_index = 9
            else:
                template_index = 14 # Default to Template O (Quad Quad Collage)

        canvas = Image.new("RGB", (PIN_W, PIN_H), WARM_WHITE)
        draw = ImageDraw.Draw(canvas)

        if Path(product_image_path).exists():
            photo = Image.open(product_image_path).convert("RGB")
        else:
            photo = Image.new("RGB", (PIN_W, PIN_H), (200, 200, 200))
            logger.warning(f"Product image not found: {product_image_path}")

        photo2 = None
        photo3 = None
        photo4 = None
        if additional_image_paths:
            if len(additional_image_paths) > 0 and Path(additional_image_paths[0]).exists():
                try:
                    photo2 = Image.open(additional_image_paths[0]).convert("RGB")
                except Exception as ex:
                    logger.warning(f"Failed to load photo2: {ex}")
            if len(additional_image_paths) > 1 and Path(additional_image_paths[1]).exists():
                try:
                    photo3 = Image.open(additional_image_paths[1]).convert("RGB")
                except Exception as ex:
                    logger.warning(f"Failed to load photo3: {ex}")
            if len(additional_image_paths) > 2 and Path(additional_image_paths[2]).exists():
                try:
                    photo4 = Image.open(additional_image_paths[2]).convert("RGB")
                except Exception as ex:
                    logger.warning(f"Failed to load photo4: {ex}")

        if photo2 is None and photo is not None:
            try:
                pw, ph = photo.size
                cw, ch = int(pw * 0.70), int(ph * 0.70)
                cx, cy = (pw - cw) // 2, int(ph * 0.12)
                photo2 = photo.crop((cx, cy, cx + cw, cy + ch))
            except Exception as ex:
                logger.warning(f"Failed to auto-crop photo2: {ex}")

        if image_style in ("collage", "card"):
            photo = _prepare_photo_for_style(photo, photo2, photo3, PIN_W, PIN_H, image_style)

        logger.info(f"Using pin template {template_index} (Style: {image_style}) for: {title[:40]}")

        trust_badges = ["FREE US SHIPPING", "USA BESTSELLER", "TRENDING IN US", "VIRAL STYLE"]
        trust_badge = trust_badges[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(trust_badges)]


        if template_index == 0:
            _template_a(draw, canvas, photo, title, category, price)
        elif template_index == 1:
            _template_b(draw, canvas, photo, title, category, price)
        elif template_index == 2:
            _template_c(draw, canvas, photo, title, category, price)
        elif template_index == 3:
            accent = _ACCENTS[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(_ACCENTS)]
            _template_d(draw, canvas, photo, title, category, price, accent=accent)
        elif template_index == 4:
            _template_e(draw, canvas, photo, title, category, price)
        elif template_index == 5:
            _template_f(draw, canvas, photo, title, category, price)
        elif template_index == 6:
            _template_g(draw, canvas, photo, title, category, price)
        elif template_index == 7:
            _template_h(draw, canvas, photo, title, category, price)
        elif template_index == 8:
            _template_i(draw, canvas, photo, title, category, price)
        elif template_index == 9:
            _template_j(draw, canvas, photo, title, category, price, cta)
        elif template_index == 10:
            _template_k(draw, canvas, photo, photo2, title, category, price)
        elif template_index == 11:
            _template_l(draw, canvas, photo, photo2, photo3, title, category, price)
        elif template_index == 12:
            _template_m(draw, canvas, photo, title, category, price)
        elif template_index == 13:
            _template_n(draw, canvas, photo, title, category, price, cta)
        elif template_index == 14:
            _template_o(draw, canvas, photo, photo2, photo3, photo4, title, category, price, trust_badge=trust_badge)
        elif template_index == 15:
            _template_p(draw, canvas, photo, title, category, price, cta)
        elif template_index == 16:
            _template_q(draw, canvas, photo, title, category, price, cta)
        else:
            _template_p(draw, canvas, photo, title, category, price, cta)

        if not output_path:
            output_path = tempfile.mktemp(suffix=".jpg", prefix="pin_final_")

        canvas.save(output_path, format="JPEG", quality=PIN_QUALITY, optimize=True)
        logger.info(f"Created overlay image: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to create pin image: {e}", exc_info=True)
        return None


# High-converting templates for Pinterest: 14 (Quad Collage), 11 (Tri-Photo), 10 (Dual Split), 15 (Editorial Hero), 16 (Lookbook Hero)
LIFESTYLE_TEMPLATES = [14, 11, 10, 15, 16, 14, 11]
ALL_TEMPLATES = [14, 11, 10, 15, 16, 0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13]
ALL_STYLES = ["collage", "carousel", "collage", "hero"]


def get_next_style_and_template(
    last_style: Optional[str] = None,
    last_template: Optional[int] = None,
    board_name: str = "",
    title: str = "",
) -> Tuple[str, int]:
    """
    Pinterest 2026 Algorithmic Priority:
    1. Heavily biases toward 'collage' (multi-image styling lookbooks) and 'carousel'.
    2. Strict 2:3 vertical aspect ratio (1000x1500 px).
    3. Multi-image templates (14, 11, 10, 15) for maximum engagement & saves.
    """
    b_lower = (board_name or "").lower()
    forced_style = os.getenv("FORCE_IMAGE_STYLE", "auto").strip().lower()

    if "blog" in b_lower:
        return ("card", 9)

    # 1. Select style (favors multi-image collage & carousel)
    if forced_style and forced_style in ALL_STYLES:
        next_style = forced_style
    elif last_style and last_style in ALL_STYLES:
        last_idx = ALL_STYLES.index(last_style)
        next_style = ALL_STYLES[(last_idx + 1) % len(ALL_STYLES)]
    else:
        next_style = "collage"

    # 2. Select next template prioritizing lifestyle collages
    if next_style in ("collage", "carousel"):
        pool = LIFESTYLE_TEMPLATES
    else:
        pool = ALL_TEMPLATES

    if last_template is not None and len(pool) > 1:
        available_templates = [t for t in pool if t != last_template]
    else:
        available_templates = pool

    if not available_templates:
        available_templates = pool

    title_hash = int(hashlib.md5(title.encode()).hexdigest(), 16)
    selected_template = available_templates[title_hash % len(available_templates)]

    return (next_style, selected_template)




def add_text_overlay(
    image_path: str,
    title: str,
    cta: str = "Shop Now",
    price: Optional[str] = None,
    output_path: Optional[str] = None,
    template_index: Optional[int] = None,
    additional_image_paths: Optional[List[str]] = None,
    board_name: str = "",
    last_style: Optional[str] = None,
    last_template: Optional[int] = None,
    image_style: Optional[str] = None,
) -> Optional[str]:
    """Called by pinterest_daily_v2.py — derives category label and handles dynamic style/template rotation."""
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

    style = image_style
    # Dynamic template & style rotation if template_index is not explicitly specified
    if template_index is None or style is None:
        next_style, template_index = get_next_style_and_template(
            last_style=last_style,
            last_template=last_template,
            board_name=board_name,
            title=title,
        )
        if style is None:
            style = next_style

    return create_pin_image(
        product_image_path=image_path,
        title=title,
        category=category,
        price=price,
        cta=cta,
        output_path=output_path,
        template_index=template_index,
        additional_image_paths=additional_image_paths,
        board_name=board_name,
        image_style=style or "hero",
    )


def generate_carousel_card_set(
    product_image_path: str,
    title: str,
    category: str = "New Arrival",
    price: Optional[str] = None,
    cta: str = "Shop Now at us.MeeeShop.com",
    output_dir: str = "/tmp",
    template_index: int = 0,
    additional_image_paths: Optional[List[str]] = None,
    board_name: str = "",
) -> List[str]:
    """
    Generate 3 to 4 distinct styled image card files for a Carousel Pin.
    Ensures 100% of products have 3-4 cards even if Shopify only provided 1 photo!
    """
    cards = []

    # Card 1: Main Hero Front View with price badge
    c1_path = str(Path(output_dir) / f"carousel_c1_{int(time.time()*1000)}.jpg")
    img1 = create_pin_image(
        product_image_path=product_image_path,
        title=title,
        category=category,
        price=price,
        cta=cta,
        output_path=c1_path,
        template_index=template_index,
        board_name=board_name,
        image_style="hero",
    )
    if img1:
        cards.append(img1)

    photo_main = Image.open(product_image_path).convert("RGB")
    pw, ph = photo_main.size

    # Card 2: Extra photo 1 or Upper Bodice / Neckline Focus Shot
    c2_path = str(Path(output_dir) / f"carousel_c2_{int(time.time()*1000)}.jpg")
    if additional_image_paths and len(additional_image_paths) > 0 and Path(additional_image_paths[0]).exists():
        sub2_path = additional_image_paths[0]
    else:
        cw, ch = int(pw * 0.70), int(ph * 0.50)
        cx, cy = (pw - cw) // 2, int(ph * 0.08)
        sub2_img = photo_main.crop((cx, cy, cx + cw, cy + ch))
        sub2_path = str(Path(output_dir) / f"carousel_sub2_{int(time.time()*1000)}.jpg")
        sub2_img.save(sub2_path)

    img2 = create_pin_image(
        product_image_path=sub2_path,
        title=f"{title} — Details & Fit",
        category=category,
        price=price,
        cta=cta,
        output_path=c2_path,
        template_index=(template_index + 1) % 13,
        board_name=board_name,
        image_style="card",
    )
    if img2:
        cards.append(img2)

    # Card 3: Extra photo 2 or Lower Hemline / Pattern Focus Shot
    c3_path = str(Path(output_dir) / f"carousel_c3_{int(time.time()*1000)}.jpg")
    if additional_image_paths and len(additional_image_paths) > 1 and Path(additional_image_paths[1]).exists():
        sub3_path = additional_image_paths[1]
    else:
        cw, ch = int(pw * 0.70), int(ph * 0.50)
        cx, cy = (pw - cw) // 2, int(ph * 0.45)
        sub3_img = photo_main.crop((cx, cy, cx + cw, cy + ch))
        sub3_path = str(Path(output_dir) / f"carousel_sub3_{int(time.time()*1000)}.jpg")
        sub3_img.save(sub3_path)

    img3 = create_pin_image(
        product_image_path=sub3_path,
        title=f"{title} — Fabric & Quality",
        category=category,
        price=price,
        cta=cta,
        output_path=c3_path,
        template_index=(template_index + 2) % 13,
        board_name=board_name,
        image_style="hero",
    )
    if img3:
        cards.append(img3)

    # Card 4: Extra photo 3 or Polaroid Style Outfit Card
    c4_path = str(Path(output_dir) / f"carousel_c4_{int(time.time()*1000)}.jpg")
    if additional_image_paths and len(additional_image_paths) > 2 and Path(additional_image_paths[2]).exists():
        sub4_path = additional_image_paths[2]
    else:
        sub4_path = product_image_path

    img4 = create_pin_image(
        product_image_path=sub4_path,
        title=f"{title} — Shop MeeeShop USA",
        category=category,
        price=price,
        cta="Shop Now at us.MeeeShop.com",
        output_path=c4_path,
        template_index=12,
        board_name=board_name,
        image_style="hero",
    )
    if img4:
        cards.append(img4)

    return cards







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
