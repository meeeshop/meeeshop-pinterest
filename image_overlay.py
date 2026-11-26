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
from typing import Optional, Tuple, List, Dict, Any



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


# ── Smooth Curved Arrow Helper ───────────────────────────────────────────────

def _draw_smooth_curved_arrow(
    draw: ImageDraw.Draw,
    start_pt: Tuple[int, int],
    control_pt: Tuple[int, int],
    end_pt: Tuple[int, int],
    color: Tuple[int, int, int] = (255, 255, 255),
    width: int = 3,
):
    """Draw smooth quadratic bezier curve with a crisp arrowhead pointing to the garment."""
    import math
    num_steps = 25
    points = []
    for i in range(num_steps + 1):
        t = i / float(num_steps)
        x = ((1 - t) ** 2) * start_pt[0] + 2 * (1 - t) * t * control_pt[0] + (t ** 2) * end_pt[0]
        y = ((1 - t) ** 2) * start_pt[1] + 2 * (1 - t) * t * control_pt[1] + (t ** 2) * end_pt[1]
        points.append((x, y))

    # Draw dark shadow contour underneath for guaranteed 100% contrast
    for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)]:
        halo_pts = [(x + dx, y + dy) for x, y in points]
        draw.line(halo_pts, fill=(10, 10, 14, 220), width=width + 2)

    draw.line(points, fill=color, width=width)

    # Arrowhead at end_pt
    p_prev = points[-4]
    dx = end_pt[0] - p_prev[0]
    dy = end_pt[1] - p_prev[1]
    angle = math.atan2(dy, dx)
    arrow_len = 16
    arrow_angle = math.pi / 5.5

    a1 = (end_pt[0] - arrow_len * math.cos(angle - arrow_angle), end_pt[1] - arrow_len * math.sin(angle - arrow_angle))
    a2 = (end_pt[0] - arrow_len * math.cos(angle + arrow_angle), end_pt[1] - arrow_len * math.sin(angle + arrow_angle))

    # Draw dark halo for arrowhead
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        draw.polygon([(end_pt[0] + dx, end_pt[1] + dy), (a1[0] + dx, a1[1] + dy), (a2[0] + dx, a2[1] + dy)], fill=(10, 10, 14, 220))

    draw.polygon([end_pt, a1, a2], fill=color)


# ── Feature Breakdown / Infographic Pin Engine ───────────────────────────────

def _render_feature_breakdown_pin(
    draw: ImageDraw.Draw,
    canvas: Image.Image,
    photo: Image.Image,
    photo2: Optional[Image.Image],
    title: str,
    category: str = "New Arrival",
    price: Optional[str] = None,
    cta: str = "SHOP THE LOOK → US.MEEESHOP.COM",
    trust_badge: Optional[str] = "FREE US SHIPPING",
    highlights: Optional[Dict[str, Any]] = None,
):
    """
    Renders high-converting 'Anatomy of a Perfect Fit' Infographic Pin:
    - Circular fabric/craftsmanship zoom-in inset with white border
    - Frosted dark glass pills with pure white & cream benefit callouts (eliminating muddy black text)
    - Left-side quick feature badges (Figure Enhancer, Stretchy Fabric, Super Soft)
    - Bold high-visibility bottom anchor bar with CTA
    """
    from content_generator_v2 import generate_product_fit_highlights

    p = _boost(_fit_image(photo, PIN_W, PIN_H))
    canvas.paste(p, (0, 0))

    overlay = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    # Bottom vignette for text anchor
    vignette_start = 1080
    vignette_height = PIN_H - vignette_start
    for i in range(vignette_height):
        progress = i / float(vignette_height)
        alpha = int(210 * (progress ** 1.35))
        ov_draw.line([(0, vignette_start + i), (PIN_W, vignette_start + i)], fill=(10, 10, 14, alpha))

    # Top subtle vignette
    for i in range(140):
        progress = 1.0 - (i / 140.0)
        alpha = int(95 * (progress ** 1.5))
        ov_draw.line([(0, i), (PIN_W, i)], fill=(10, 10, 14, alpha))

    CREAM_WHITE    = (255, 255, 255, 255)
    CHAMPAGNE_GOLD = (255, 230, 130, 255)
    WARM_OAT       = (255, 245, 225, 255)
    FROSTED_GLASS  = (15, 15, 20, 205)       # 80% opacity luxury dark glass
    SHADOW_DARK    = (5, 5, 8, 250)

    def draw_bold_shadowed(d, pos, text, font, fill=CREAM_WHITE, anchor=None):
        x, y = pos
        offsets = [(-3,0), (3,0), (0,-3), (0,3), (-2,-2), (2,2), (-2,2), (2,-2), (-1,-1), (1,1)]
        for dx, dy in offsets:
            if anchor:
                d.text((x + dx, y + dy), text, fill=SHADOW_DARK, font=font, anchor=anchor)
            else:
                d.text((x + dx, y + dy), text, fill=SHADOW_DARK, font=font)
        if anchor:
            d.text((x, y), text, fill=fill, font=font, anchor=anchor)
        else:
            d.text((x, y), text, fill=fill, font=font)

    def draw_callout_pill(d, x, y, title_text, desc_text, align="left"):
        """Draw a frosted glass pill containing bold white title and warm cream description."""
        t_font = _get_font(24, bold=True)
        d_font = _get_font(20, bold=False)
        
        t_box = t_font.getbbox(title_text)
        d_box = d_font.getbbox(desc_text)
        
        t_w = t_box[2] - t_box[0]
        d_w = d_box[2] - d_box[0]
        max_w = max(t_w, d_w)
        
        pad_x, pad_y = 20, 12
        card_w = max_w + pad_x * 2
        card_h = (t_box[3] - t_box[1]) + (d_box[3] - d_box[1]) + pad_y * 2 + 6
        
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
        
        _draw_rounded_rect(d, (rx1, ry1, rx2, ry2), r=14, fill=FROSTED_GLASS)
        
        if align == "right":
            d.text((rx2 - pad_x, ry1 + pad_y), title_text, fill=CREAM_WHITE, font=t_font, anchor="ra")
            d.text((rx2 - pad_x, ry1 + pad_y + 28), desc_text, fill=WARM_OAT, font=d_font, anchor="ra")
        elif align == "center":
            d.text((rx1 + card_w // 2, ry1 + pad_y), title_text, fill=CREAM_WHITE, font=t_font, anchor="ma")
            d.text((rx1 + card_w // 2, ry1 + pad_y + 28), desc_text, fill=WARM_OAT, font=d_font, anchor="ma")
        else:
            d.text((rx1 + pad_x, ry1 + pad_y), title_text, fill=CREAM_WHITE, font=t_font)
            d.text((rx1 + pad_x, ry1 + pad_y + 28), desc_text, fill=WARM_OAT, font=d_font)
            
        return (rx1, ry1, rx2, ry2)

    if not highlights:
        highlights = generate_product_fit_highlights({"title": title, "product_type": category})

    # 1. Top-Left Headline ("A NEW KIND OF LUXE" in Champagne Gold / White)
    h_sub = highlights.get("top_header_sub", "A NEW KIND OF")
    h_main = highlights.get("top_header_main", "LUXE")
    draw_bold_shadowed(ov_draw, (45, 40), h_sub, _get_font(20, bold=True), fill=CHAMPAGNE_GOLD)
    draw_bold_shadowed(ov_draw, (45, 65), h_main, _get_font(52, bold=True), fill=CREAM_WHITE)

    # 2. Top-Right Trust Badge Pill
    tb_text = f"★  {(trust_badge or 'FREE US SHIPPING').upper()}"
    tb_font = _get_font(30, bold=True)
    tb_box = tb_font.getbbox(tb_text)
    tb_w = tb_box[2] - tb_box[0]
    tb_h = tb_box[3] - tb_box[1]
    pill_w = tb_w + 48
    pill_h = tb_h + 24
    pill_x = PIN_W - pill_w - 45
    pill_y = 45
    _draw_rounded_rect(ov_draw, (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h), r=pill_h // 2, fill=FROSTED_GLASS)
    ov_draw.text((pill_x + 24, pill_y + 12), tb_text, fill=CREAM_WHITE, font=tb_font)

    # 3. Circular Detail Zoom Inset (x=240, y=310, dia=210)
    zoom_dia = 210
    zoom_r = zoom_dia // 2
    zx, zy = 240, 310
    
    if photo2 is not None:
        zoom_src = photo2
    else:
        pw, ph = photo.size
        cw, ch = int(pw * 0.40), int(ph * 0.30)
        cx, cy = (pw - cw) // 2, int(ph * 0.40)
        zoom_src = photo.crop((cx, cy, cx + cw, cy + ch))
    
    zoom_fit = _boost(_fit_image(zoom_src, zoom_dia, zoom_dia))
    
    mask = Image.new("L", (zoom_dia, zoom_dia), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, zoom_dia, zoom_dia), fill=255)
    canvas.paste(zoom_fit, (zx - zoom_r, zy - zoom_r), mask)
    ImageDraw.Draw(canvas).ellipse((zx - zoom_r - 2, zy - zoom_r - 2, zx + zoom_r + 2, zy + zoom_r + 2), outline=(255, 255, 255), width=5)

    # 4. Feature Callout 1 (Right Waist / Panels) — Frosted Pill with White/Cream Text
    c1 = highlights.get("callout_waist", {})
    t1_title = c1.get("title", "Contour waistbands")
    t1_desc = c1.get("desc", "and slimming panels that hug your body")
    pill1_rect = draw_callout_pill(ov_draw, 520, 320, t1_title, t1_desc, align="left")
    _draw_smooth_curved_arrow(ov_draw, start_pt=(pill1_rect[0] + 40, pill1_rect[3]), control_pt=(580, 420), end_pt=(560, 430), color=(255, 255, 255))

    # 5. Feature Callout 2 (Center Left / Detail Zoom)
    c2 = highlights.get("callout_zoom", {})
    t2_title = c2.get("title", "Heart-shaped yoke")
    t2_desc = c2.get("desc", "gives that natural lift")
    pill2_rect = draw_callout_pill(ov_draw, 240, 425, t2_title, t2_desc, align="center")
    _draw_smooth_curved_arrow(ov_draw, start_pt=(pill2_rect[1] + 30, pill2_rect[3]), control_pt=(360, 485), end_pt=(405, 475), color=(255, 255, 255))

    # 6. Feature Callout 3 (Left Pocket / Silhouette)
    c3 = highlights.get("callout_pocket", {})
    t3_title = c3.get("title", "Short back pockets")
    t3_desc = c3.get("desc", "make your silhouette look fuller")
    pill3_rect = draw_callout_pill(ov_draw, 420, 535, t3_title, t3_desc, align="right")
    _draw_smooth_curved_arrow(ov_draw, start_pt=(pill3_rect[2], pill3_rect[1] + 25), control_pt=(450, 545), end_pt=(480, 530), color=(255, 255, 255))

    # 7. Feature Callout 4 (Lower Leg / Stretch)
    c4 = highlights.get("callout_fabric", {})
    t4_title = c4.get("title", "2% Spandex blend.")
    t4_desc = c4.get("desc", "Hugs your curves and moves with you.")
    pill4_rect = draw_callout_pill(ov_draw, 520, 730, t4_title, t4_desc, align="left")
    _draw_smooth_curved_arrow(ov_draw, start_pt=(pill4_rect[0] + 30, pill4_rect[1] + 20), control_pt=(500, 755), end_pt=(470, 750), color=(255, 255, 255))

    # 8. Left Feature Attribute Badges (Column at x=20, y=930..1280)
    badges = highlights.get("badges", ["Figure Enhancer", "Stretchy Fabric", "Super Soft"])
    b_y = 930
    for b_text in badges[:3]:
        card_w, card_h = 135, 105
        _draw_rounded_rect(ov_draw, (20, b_y, 20 + card_w, b_y + card_h), r=16, fill=FROSTED_GLASS)
        ov_draw.text((20 + card_w // 2, b_y + 20), "★", fill=CHAMPAGNE_GOLD, font=_get_font(26, bold=True), anchor="mt")
        b_lines = _wrap_text(b_text, _get_font(18, bold=True), max_width=card_w - 10)
        for li, line in enumerate(b_lines[:2]):
            ov_draw.text((20 + card_w // 2, b_y + 55 + li * 20), line, fill=CREAM_WHITE, font=_get_font(16, bold=True), anchor="mt")
        b_y += card_h + 14

    # 9. Bottom Anchor Bar
    hook_text = "M E E E S H O P  •  N E W  A R R I V A L S"
    hook_font = _get_font(25, bold=True)
    draw_bold_shadowed(ov_draw, (PIN_W // 2, 1165), hook_text, hook_font, fill=CHAMPAGNE_GOLD, anchor="mt")

    clean_title = (title or "").strip()
    for leak in ["we need", "create a", "product:", "type:"]:
        if leak in clean_title.lower():
            clean_title = "Trending Boutique Style"
            break

    price_str = f"${float(str(price).replace('$', '')):.2f}" if price and any(c.isdigit() for c in str(price)) else ""
    sub_text = f"{price_str}   •   FREE US SHIPPING   •   TRUE-TO-SIZE FIT" if price_str else "FREE US SHIPPING   •   TRUE-TO-SIZE FIT"
    draw_bold_shadowed(ov_draw, (PIN_W // 2, 1265), sub_text, _get_font(32, bold=True), fill=WARM_OAT, anchor="mt")

    # CTA Button
    cta_btn_w = 640
    cta_btn_h = 72
    cta_btn_x = (PIN_W - cta_btn_w) // 2
    cta_btn_y = 1345
    _draw_rounded_rect(ov_draw, (cta_btn_x, cta_btn_y, cta_btn_x + cta_btn_w, cta_btn_y + cta_btn_h), r=cta_btn_h // 2, fill=(255, 255, 255, 250))
    cta_font = _get_font(28, bold=True)
    ov_draw.text((PIN_W // 2, cta_btn_y + 19), "SHOP THE LOOK  →  US.MEEESHOP.COM", fill=(15, 15, 20, 255), font=cta_font, anchor="mt")

    # Merge overlay onto canvas
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"), (0, 0))


# ── Editorial Blog Pin Engine (Reference Matched) ─────────────────────────
def _render_editorial_blog_pin(
    draw: ImageDraw.Draw,
    canvas: Image.Image,
    photo: Image.Image,
    title: str,
    category: str = "STYLE GUIDE",
    cta: str = "READ THE FULL GUIDE ->",
):
    """
    Sleek editorial layout matching Pinterest aesthetic blog pins.
    - Subtle left/top vignette
    - Aesthetic serif typography
    - Floating CTA and minimalist bottom branding
    """
    p = _boost(_fit_image(photo, PIN_W, PIN_H))
    canvas.paste(p, (0, 0))

    overlay = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    # 1. Subtle Dark Wash (Vignette) on left and top for text readability
    for i in range(1200):
        progress = 1.0 - (i / 1200.0)
        alpha = int(140 * (progress ** 1.5))
        ov_draw.line([(0, i), (PIN_W, i)], fill=(20, 20, 20, alpha))
        
    for x in range(900):
        progress = 1.0 - (x / 900.0)
        alpha = int(110 * (progress ** 1.5))
        ov_draw.line([(x, 0), (x, PIN_H)], fill=(20, 20, 20, alpha))

    # Palettes
    CREAM_WHITE = (255, 250, 240, 255)
    WARM_ACCENT = (235, 195, 155, 255) 

    # Helper for crisp shadowed text
    def draw_shadowed_text(d, pos, text, font, fill=CREAM_WHITE, anchor=None):
        x, y = pos
        offsets = [(-2,0), (2,0), (0,-2), (0,2), (-1,-1), (1,1)]
        for dx, dy in offsets:
            d.text((x + dx, y + dy), text, fill=(10, 10, 10, 200), font=font, anchor=anchor)
        d.text((x, y), text, fill=fill, font=font, anchor=anchor)

    # 2. Category Label (Top Left)
    cat_font = _get_font(28, bold=True)
    draw_shadowed_text(ov_draw, (70, 80), (category or "STYLE GUIDE").upper(), cat_font, fill=WARM_ACCENT)
    
    # 3. Main Title (Large Editorial Serif)
    title_font = _get_font(105, bold=True, serif=True)
    title_lines = _wrap_text(title, title_font, max_width=PIN_W - 140)
    
    y_pos = 160
    for line in title_lines:
        draw_shadowed_text(ov_draw, (70, y_pos), line, title_font, fill=CREAM_WHITE)
        y_pos += 115
        
    # 4. CTA Pill
    cta_y = y_pos + 60
    cta_w = 460
    cta_h = 60
    _draw_rounded_rect(ov_draw, (70, cta_y, 70 + cta_w, cta_y + cta_h), r=8, fill=(235, 195, 155, 240))
    cta_font = _get_font(24, bold=True)
    ov_draw.text((70 + cta_w // 2, cta_y + 30), cta.upper(), fill=(20, 20, 20, 255), font=cta_font, anchor="mm")
    
    # 5. Bottom Branding
    draw_shadowed_text(ov_draw, (70, PIN_H - 120), "MEEESHOP", _get_font(36, bold=True, serif=True), fill=CREAM_WHITE)
    draw_shadowed_text(ov_draw, (70, PIN_H - 70), "Dressed for where the day goes.", _get_font(22, italic=True, serif=True), fill=CREAM_WHITE)

    # Merge overlay
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"), (0, 0))


# ── 2026 Trending E-Commerce Brand Pin Templates (7 Exclusive Formats) ──────
# Modeled strictly on high-performing US e-commerce Pinterest pins (Macy's, Target, Kohl's)
# plus direct clean product photos without overlay text:
#   0 — Parchment Occasion Collage (Macy's Image 1: textured parchment + gold confetti + serif headline + hero left + 3 right)
#   1 — Trend Spotlight Collage (Macy's Image 2: clean parchment + "TREND SPOTLIGHT" + serif "How to Style..." + hero left + 3 right)
#   2 — Jewel-Tone Podium Showcase (Target Image 3: deep jewel gradient + circular badge headline + layered product podiums)
#   3 — Bold Editorial Solid (Target Image 4: rich solid color + bold white headline + large lower lifestyle hero)
#   4 — Forest Hero + Pill Badge (Target Image 5: deep forest/plum solid + centered white headline + hero product + white pill badge)
#   5 — Top Banner + Full-Bleed Photo (Kohl's Image 6: bold top color header banner + full-bleed photo + subtle bottom wordmark)
#   6 — Direct Clean Product Photo (Zero overlay text, zero logos, pure 2:3 polished product photography)

from PIL import ImageFilter

PARCHMENT_BG = (245, 238, 228)
CHARCOAL     = (44,  42,  40)
GOLD_ACCENT  = (188, 152, 92)
BRAND_RED    = (210, 35,  45)


def _create_parchment_bg(seed_text: str = "", with_confetti: bool = False) -> Image.Image:
    """Create a warm textured parchment background with optional gold/bronze confetti at top & bottom."""
    import random
    rng = random.Random(hashlib.md5(seed_text.encode()).hexdigest())
    canvas = Image.new("RGB", (PIN_W, PIN_H), PARCHMENT_BG)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Subtle warm organic mottling patches
    for _ in range(45):
        cx = rng.randint(0, PIN_W)
        cy = rng.randint(0, PIN_H)
        rx = rng.randint(80, 260)
        ry = rng.randint(80, 260)
        tone = rng.choice([(236, 224, 210, 28), (250, 245, 238, 32), (228, 212, 194, 22)])
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=tone)

    if with_confetti:
        confetti_colors = [
            (194, 155, 85, 190),
            (168, 128, 62, 175),
            (218, 185, 120, 165),
            (130, 96, 48, 140),
        ]
        # Top & bottom border sparkle clusters (like Macy's Image 1)
        for _ in range(95):
            x = rng.randint(15, PIN_W - 15)
            y = rng.randint(10, 230) if rng.random() < 0.52 else rng.randint(PIN_H - 220, PIN_H - 10)
            r = rng.randint(2, 6)
            col = rng.choice(confetti_colors)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=col)

    return canvas.filter(ImageFilter.GaussianBlur(radius=0.6))


def _paste_rounded_shadow(
    canvas: Image.Image,
    img: Image.Image,
    box: Tuple[int, int, int, int],
    radius: int = 16,
    shadow_alpha: int = 45,
) -> None:
    """Fit img into box (x0, y0, x1, y1), round corners, and paste with a soft drop shadow."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    fitted = _boost(_fit_image(img, w, h)).convert("RGBA")

    # Rounded mask
    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    _draw_rounded_rect(mdraw, (0, 0, w, h), radius, 255)
    fitted.putalpha(mask)

    # Soft shadow layer
    if shadow_alpha > 0:
        pad = 18
        shadow = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        _draw_rounded_rect(sdraw, (pad, pad + 6, w + pad, h + pad + 6), radius, (20, 18, 16, shadow_alpha))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
        canvas.paste(shadow, (x0 - pad, y0 - pad), shadow)

    canvas.paste(fitted, (x0, y0), fitted)


def _draw_brand_wordmark(draw: ImageDraw.Draw, y_center: int, dark: bool = True) -> None:
    """Draw clean minimalist brand wordmark at bottom center (Macy's / Kohl's style)."""
    text_col = CHARCOAL if dark else WHITE
    star_col = BRAND_RED if dark else (255, 220, 220)
    wf = _get_font(34, bold=False)
    word = "meeeshop"
    wb = wf.getbbox(word)
    ww = wb[2] - wb[0]
    star = "★"
    sf = _get_font(32, bold=True)
    sb = sf.getbbox(star)
    sw = sb[2] - sb[0]
    total_w = sw + 10 + ww
    sx = (PIN_W - total_w) // 2
    draw.text((sx, y_center), star, fill=star_col, font=sf, anchor="lm")
    draw.text((sx + sw + 10, y_center), word, fill=text_col, font=wf, anchor="lm")


def _draw_minimal_brand_mark(draw: ImageDraw.Draw, x: int = 58, y: int = PIN_H - 72, color: Tuple = WHITE) -> None:
    """Draw minimalist Target-style concentric brand ring mark in bottom-left."""
    r_outer = 24
    r_inner = 10
    draw.ellipse([x - r_outer, y - r_outer, x + r_outer, y + r_outer], outline=color, width=7)
    draw.ellipse([x - r_inner, y - r_inner, x + r_inner, y + r_inner], fill=color)


def _derive_editorial_headline(title: str, category: str, mode: str = "occasion") -> Tuple[str, str]:
    """Build clean, short 2-5 word editorial headlines from product title/category (no SKU clutter)."""
    clean_cat = (category or "Style").replace("Trending:", "").strip()
    if not clean_cat or clean_cat == "New Arrival":
        clean_cat = "Boutique Styles"

    tl = (title or "").lower()
    if mode == "spotlight":
        if "dress" in tl:
            return "TREND SPOTLIGHT", "How to Style\nMidi Dresses"
        if "jean" in tl or "denim" in tl:
            return "TREND SPOTLIGHT", "How to Style\nFlare Denim"
        if "sweater" in tl or "cardigan" in tl or "knit" in tl:
            return "TREND SPOTLIGHT", "How to Style\nCozy Knits"
        if "bag" in tl or "tote" in tl or "crossbody" in tl:
            return "TREND SPOTLIGHT", "How to Style\nEveryday Bags"
        if "boot" in tl or "shoe" in tl or "heel" in tl or "flat" in tl:
            return "TREND SPOTLIGHT", "How to Style\nChic Footwear"
        return "TREND SPOTLIGHT", f"How to Style\n{clean_cat}"

    # Short clean title for occasion / gift / editorial templates
    words = [w for w in (title or "").replace("|", " ").replace("-", " ").split() if len(w) > 1 and not w.startswith("$")]
    short = " ".join(words[:4]) if words else clean_cat
    if len(short) > 26:
        short = " ".join(words[:3])
    return clean_cat.upper(), short


def _extract_sub_photos(photo: Image.Image, photo2: Optional[Image.Image], photo3: Optional[Image.Image], photo4: Optional[Image.Image]) -> List[Image.Image]:
    """Ensure 3 secondary product/detail images are available for multi-item collage templates."""
    pw, ph = photo.size
    fallbacks = [
        photo.crop((int(pw * 0.15), int(ph * 0.05), int(pw * 0.85), int(ph * 0.52))),
        photo.crop((int(pw * 0.15), int(ph * 0.30), int(pw * 0.85), int(ph * 0.78))),
        photo.crop((int(pw * 0.15), int(ph * 0.52), int(pw * 0.85), int(ph * 0.96))),
    ]
    subs = [p for p in (photo2, photo3, photo4) if p is not None]
    while len(subs) < 3:
        subs.append(fallbacks[len(subs) % len(fallbacks)])
    return subs[:3]


def _render_parchment_occasion_collage(
    canvas: Image.Image,
    photo: Image.Image,
    photo2: Optional[Image.Image],
    photo3: Optional[Image.Image],
    photo4: Optional[Image.Image],
    title: str,
    category: str,
) -> None:
    """Template 0 (Macy's Image 1): Warm parchment + subtle gold confetti + serif headline + hero left + 3 right."""
    bg = _create_parchment_bg(title, with_confetti=True)
    canvas.paste(bg, (0, 0))
    draw = ImageDraw.Draw(canvas)

    _, short_title = _derive_editorial_headline(title, category, mode="occasion")
    headline = f"{short_title}\nfor the Occasion" if len(short_title) <= 18 else short_title
    h_font = _get_font(68, bold=True, serif=True)
    lines = _wrap_text(headline.replace("\n", " "), h_font, PIN_W - 140)[:2]
    if "\n" in headline:
        lines = headline.split("\n")[:2]
    y_text = 75
    for line in lines:
        draw.text((PIN_W // 2, y_text), line, fill=CHARCOAL, font=h_font, anchor="mt")
        y_text += 78

    # Hero left + 3 stacked cutouts right
    top_y = max(255, y_text + 26)
    bot_y = PIN_H - 135
    _paste_rounded_shadow(canvas, photo, (48, top_y, 505, bot_y), radius=18, shadow_alpha=38)

    subs = _extract_sub_photos(photo, photo2, photo3, photo4)
    gap = 22
    slot_h = (bot_y - top_y - 2 * gap) // 3
    for idx, sub_img in enumerate(subs):
        sy0 = top_y + idx * (slot_h + gap)
        _paste_rounded_shadow(canvas, sub_img, (532, sy0, PIN_W - 48, sy0 + slot_h), radius=18, shadow_alpha=36)

    _draw_brand_wordmark(draw, PIN_H - 68, dark=True)


def _render_trend_spotlight_collage(
    canvas: Image.Image,
    photo: Image.Image,
    photo2: Optional[Image.Image],
    photo3: Optional[Image.Image],
    photo4: Optional[Image.Image],
    title: str,
    category: str,
) -> None:
    """Template 1 (Macy's Image 2): Clean parchment + TREND SPOTLIGHT eyebrow + serif headline + hero left + 3 right."""
    bg = _create_parchment_bg(title + "_spot", with_confetti=False)
    canvas.paste(bg, (0, 0))
    draw = ImageDraw.Draw(canvas)

    eyebrow, headline = _derive_editorial_headline(title, category, mode="spotlight")
    e_font = _get_font(24, bold=True)
    draw.text((PIN_W // 2, 56), eyebrow, fill=CHARCOAL, font=e_font, anchor="mt")

    h_font = _get_font(70, bold=True, serif=True)
    lines = headline.split("\n")[:2]
    y_text = 104
    for line in lines:
        draw.text((PIN_W // 2, y_text), line, fill=CHARCOAL, font=h_font, anchor="mt")
        y_text += 78

    top_y = 285
    bot_y = PIN_H - 135
    _paste_rounded_shadow(canvas, photo, (48, top_y, 505, bot_y), radius=18, shadow_alpha=36)

    subs = _extract_sub_photos(photo, photo2, photo3, photo4)
    gap = 22
    slot_h = (bot_y - top_y - 2 * gap) // 3
    for idx, sub_img in enumerate(subs):
        sy0 = top_y + idx * (slot_h + gap)
        _paste_rounded_shadow(canvas, sub_img, (532, sy0, PIN_W - 48, sy0 + slot_h), radius=18, shadow_alpha=36)

    _draw_brand_wordmark(draw, PIN_H - 68, dark=True)


def _render_jewel_podium_showcase(
    canvas: Image.Image,
    photo: Image.Image,
    photo2: Optional[Image.Image],
    photo3: Optional[Image.Image],
    title: str,
    category: str,
) -> None:
    """Template 2 (Target Image 3): Jewel-tone radial gradient + circular badge headline + layered product podiums."""
    palettes = [
        ((8, 86, 78), (4, 58, 52), (48, 128, 118)),     # Deep Emerald Teal (Target Image 3)
        ((86, 26, 64), (58, 16, 44), (130, 56, 100)),   # Rich Berry Plum
        ((24, 54, 92), (14, 34, 64), (58, 96, 142)),    # Deep Sapphire
    ]
    base_col, dark_col, podium_col = palettes[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(palettes)]

    canvas.paste(Image.new("RGB", (PIN_W, PIN_H), base_col), (0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Subtle radial glow behind products
    draw.ellipse([120, 320, 880, 1150], fill=(255, 255, 255, 18))

    # Top-left circular headline badge
    cx, cy, rad = 285, 295, 195
    draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=dark_col + (245,))
    _, short_title = _derive_editorial_headline(title, category)
    h_font = _get_font(46, bold=True)
    lines = _wrap_text(short_title, h_font, rad * 2 - 70)[:3]
    total_h = len(lines) * 54
    ty = cy - total_h // 2 + 24
    for line in lines:
        draw.text((cx, ty), line, fill=WHITE, font=h_font, anchor="mm")
        ty += 54

    # Draw 3D-style circular pedestals + layered product cards
    # Back-right podium
    p2 = photo2 if photo2 is not None else photo
    draw.ellipse([540, 1020, 950, 1125], fill=podium_col + (240,))
    draw.rectangle([540, 1072, 950, 1155], fill=dark_col + (220,))
    draw.ellipse([540, 1110, 950, 1200], fill=dark_col + (220,))
    _paste_rounded_shadow(canvas, p2, (565, 420, 925, 1060), radius=20, shadow_alpha=55)

    # Front-left/center hero podium
    draw.ellipse([110, 1110, 740, 1230], fill=podium_col + (255,))
    draw.rectangle([110, 1170, 740, 1265], fill=dark_col + (235,))
    draw.ellipse([110, 1215, 740, 1315], fill=dark_col + (235,))
    _paste_rounded_shadow(canvas, photo, (165, 535, 685, 1170), radius=22, shadow_alpha=65)

    _draw_minimal_brand_mark(draw, x=78, y=PIN_H - 72, color=WHITE)


def _render_bold_editorial_solid(
    canvas: Image.Image,
    photo: Image.Image,
    title: str,
    category: str,
) -> None:
    """Template 3 (Target Image 4): Rich solid color + bold white top headline + large lower lifestyle hero."""
    solids = [
        (114, 18, 28),   # Rich Burgundy Wine (Target Image 4)
        (28, 46, 74),    # Midnight Navy
        (132, 62, 46),   # Warm Terracotta
        (56, 36, 54),    # Deep Aubergine
    ]
    bg_col = solids[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(solids)]
    canvas.paste(Image.new("RGB", (PIN_W, PIN_H), bg_col), (0, 0))
    draw = ImageDraw.Draw(canvas)

    _, short_title = _derive_editorial_headline(title, category)
    h_font = _get_font(60, bold=True)
    lines = _wrap_text(short_title, h_font, PIN_W - 120)[:2]
    y_text = 105
    for line in lines:
        draw.text((PIN_W // 2, y_text), line, fill=WHITE, font=h_font, anchor="mt")
        y_text += 72

    # Clean large lower hero photo
    top_y = max(275, y_text + 45)
    _paste_rounded_shadow(canvas, photo, (46, top_y, PIN_W - 46, PIN_H - 46), radius=24, shadow_alpha=45)
    _draw_minimal_brand_mark(draw, x=88, y=PIN_H - 88, color=WHITE)


def _render_forest_hero_pill(
    canvas: Image.Image,
    photo: Image.Image,
    title: str,
    category: str,
) -> None:
    """Template 4 (Target Image 5): Deep forest green solid + centered headline + hero product + white pill badge."""
    solids = [
        (16, 86, 44),    # Deep Forest Green (Target Image 5)
        (44, 72, 62),    # Sage Slate
        (82, 44, 58),    # Mulberry
    ]
    bg_col = solids[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(solids)]
    canvas.paste(Image.new("RGB", (PIN_W, PIN_H), bg_col), (0, 0))
    draw = ImageDraw.Draw(canvas)

    _, short_title = _derive_editorial_headline(title, category)
    h_font = _get_font(56, bold=True)
    lines = _wrap_text(short_title, h_font, PIN_W - 120)[:2]
    y_text = 108
    for line in lines:
        draw.text((PIN_W // 2, y_text), line, fill=WHITE, font=h_font, anchor="mt")
        y_text += 66

    sub_font = _get_font(38, bold=False)
    draw.text((PIN_W // 2, y_text + 8), "from MeeeShop", fill=(235, 242, 236), font=sub_font, anchor="mt")

    # Centered hero product card
    _paste_rounded_shadow(canvas, photo, (105, 345, PIN_W - 105, 1265), radius=22, shadow_alpha=60)

    # Bottom-left white pill badge
    pill_box = (0, 1345, 345, 1445)
    _draw_rounded_rect(draw, (-20, pill_box[1], pill_box[2], pill_box[3]), 48, WHITE)
    # Small bag icon + text
    bx, by = 52, 1372
    draw.rectangle([bx, by + 12, bx + 38, by + 50], fill=BRAND_RED)
    draw.arc([bx + 8, by, bx + 30, by + 24], 180, 360, fill=BRAND_RED, width=4)
    p_font = _get_font(26, bold=True)
    draw.text((108, 1395), "free US shipping", fill=CHARCOAL, font=p_font, anchor="lm")


def _render_top_banner_fullbleed(
    canvas: Image.Image,
    photo: Image.Image,
    title: str,
    category: str,
) -> None:
    """Template 5 (Kohl's Image 6): Bold top color banner + full-bleed edge-to-edge photo + bottom wordmark."""
    banners = [
        (225, 22, 34),   # Crimson Red (Kohl's Image 6)
        (168, 68, 52),   # Warm Terracotta
        (28, 48, 82),    # Classic Navy
    ]
    banner_col = banners[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(banners)]
    banner_h = 335

    # Full-bleed bottom photo
    hero = _boost(_fit_image(photo, PIN_W, PIN_H - banner_h + 10))
    canvas.paste(hero, (0, banner_h - 10))

    # Top solid banner
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, PIN_W, banner_h], fill=banner_col)

    # Small icon + eyebrow + bold headline
    eyebrow_font = _get_font(30, bold=True)
    draw.text((PIN_W // 2, 118), "MeeeShop Style Edit", fill=WHITE, font=eyebrow_font, anchor="mm")

    _, short_title = _derive_editorial_headline(title, category)
    h_font = _get_font(54, bold=True)
    h_fit, h_txt = _fit_text(short_title, bold=True, max_w=PIN_W - 100, start_size=54, min_size=34)
    draw.text((PIN_W // 2, 210), h_txt, fill=WHITE, font=h_fit, anchor="mm")

    # Subtle clean bottom footer wordmark
    overlay = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([0, PIN_H - 95, PIN_W, PIN_H], fill=(255, 255, 255, 210))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(canvas)
    f_font = _get_font(26, bold=True)
    draw.text((PIN_W // 2, PIN_H - 48), "SHOP NOW AT MEEESHOP", fill=banner_col, font=f_font, anchor="mm")


def _render_direct_clean_photo(canvas: Image.Image, photo: Image.Image) -> None:
    """Template 6: Direct product photo with ZERO overlay text, zero logos, pure 2:3 polished photography."""
    clean = _boost(_fit_image(photo, PIN_W, PIN_H))
    canvas.paste(clean, (0, 0))


def _prepare_photo_for_style(
    photo: Image.Image,
    photo2: Optional[Image.Image],
    photo3: Optional[Image.Image],
    target_w: int,
    target_h: int,
    style: str,
) -> Image.Image:
    """Fit product photo into target_w x target_h with color/sharpness boost."""
    return _boost(_fit_image(photo, target_w, target_h))


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
    Create a Pinterest pin using ONLY the 7 trending e-commerce templates (0..6):
      0 = Parchment Occasion Collage (Macy's style)
      1 = Trend Spotlight Collage (Macy's style)
      2 = Jewel-Tone Podium Showcase (Target style)
      3 = Bold Editorial Solid (Target style)
      4 = Forest Hero + Pill Badge (Target style)
      5 = Top Banner + Full-Bleed Photo (Kohl's style)
      6 = Direct Clean Product Photo (Zero overlay text)
    """
    try:
        if template_index is None:
            template_index = int(hashlib.md5((title or "pin").encode()).hexdigest(), 16) % 7
        else:
            template_index = int(template_index) % 7

        canvas = Image.new("RGB", (PIN_W, PIN_H), PARCHMENT_BG)

        if Path(product_image_path).exists():
            photo = Image.open(product_image_path).convert("RGB")
        else:
            photo = Image.new("RGB", (PIN_W, PIN_H), (225, 220, 214))
            logger.warning(f"Product image not found: {product_image_path}")

        photo2, photo3, photo4 = None, None, None
        if additional_image_paths:
            loaded = []
            for p in additional_image_paths[:3]:
                if p and Path(p).exists():
                    try:
                        loaded.append(Image.open(p).convert("RGB"))
                    except Exception as ex:
                        logger.warning(f"Failed to load extra image {p}: {ex}")
            if len(loaded) > 0:
                photo2 = loaded[0]
            if len(loaded) > 1:
                photo3 = loaded[1]
            if len(loaded) > 2:
                photo4 = loaded[2]

        logger.info(f"Using trending e-commerce pin template {template_index}/6 for: {title[:40]}")

        if template_index == 0:
            _render_parchment_occasion_collage(canvas, photo, photo2, photo3, photo4, title, category)
        elif template_index == 1:
            _render_trend_spotlight_collage(canvas, photo, photo2, photo3, photo4, title, category)
        elif template_index == 2:
            _render_jewel_podium_showcase(canvas, photo, photo2, photo3, title, category)
        elif template_index == 3:
            _render_bold_editorial_solid(canvas, photo, title, category)
        elif template_index == 4:
            _render_forest_hero_pill(canvas, photo, title, category)
        elif template_index == 5:
            _render_top_banner_fullbleed(canvas, photo, title, category)
        else:
            _render_direct_clean_photo(canvas, photo)

        if not output_path:
            output_path = tempfile.mktemp(suffix=".jpg", prefix="pin_final_")

        canvas.save(output_path, format="JPEG", quality=PIN_QUALITY, optimize=True)
        logger.info(f"Created trending template pin image ({template_index}): {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Failed to create pin image: {e}", exc_info=True)
        return None


# Exclusive 7-template rotation (0..5 branded e-commerce templates + 6 direct clean product photo)
TRENDING_TEMPLATES = [0, 1, 2, 3, 4, 5, 6]
LIFESTYLE_TEMPLATES = TRENDING_TEMPLATES
ALL_TEMPLATES = TRENDING_TEMPLATES
ALL_STYLES = ["collage", "hero", "clean"]


def get_next_style_and_template(
    last_style: Optional[str] = None,
    last_template: Optional[int] = None,
    board_name: str = "",
    title: str = "",
) -> Tuple[str, int]:
    """
    Strictly rotate across the 7 exclusive trending e-commerce templates (0..6)
    including direct clean product photos (6) so consecutive pins never repeat the same layout.
    """
    if last_template is not None and isinstance(last_template, int):
        next_template = (last_template + 1) % len(TRENDING_TEMPLATES)
    else:
        title_hash = int(hashlib.md5((title or "pin").encode()).hexdigest(), 16)
        next_template = TRENDING_TEMPLATES[title_hash % len(TRENDING_TEMPLATES)]

    if next_template == 6:
        next_style = "clean"
    elif next_template in (0, 1, 2):
        next_style = "collage"
    else:
        next_style = "hero"

    return (next_style, next_template)




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
