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
CORAL      = (232, 93,  78)
NAVY       = (22,  43,  77)
SAGE       = (88,  120, 90)
BLUSH      = (230, 185, 175)


# ── Font helpers ─────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont:
    if serif:
        candidates = (
            [
                "C:/Windows/Fonts/georgiab.ttf",
                "C:/Windows/Fonts/timesbd.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                "georgiab.ttf",
            ] if bold else [
                "C:/Windows/Fonts/georgia.ttf",
                "C:/Windows/Fonts/times.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                "georgia.ttf",
            ]
        )
    else:
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


# ── Template F ───────────────────────────────────────────────────────────────
# Poetcore Storybook Editorial: linen bg, centered photo with double border,
# editorial serif typography, typewriter price tag.
def _template_f(draw, canvas, photo, title, category, price):
    bg_color = (246, 243, 238)
    draw.rectangle([(0, 0), (PIN_W, PIN_H)], fill=bg_color)

    HEADER_H = int(PIN_H * 0.16)
    FOOTER_H = int(PIN_H * 0.18)
    CTA_H = int(PIN_H * 0.10)
    PHOTO_H = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD = int(PIN_W * 0.08)

    # Category top center (Georgia / Serif, italic)
    cf = _get_font(int(HEADER_H * 0.28), bold=False, serif=True)
    cb = cf.getbbox(category)
    draw.text(((PIN_W - (cb[2]-cb[0])) // 2, int(HEADER_H * 0.35)), category, fill=DARK_GREY, font=cf)

    # Photo centered with double thin borders
    photo_w = PIN_W - PAD * 2
    photo_h = PHOTO_H - PAD
    p = _boost(_fit_image(photo, photo_w, photo_h))
    canvas.paste(p, (PAD, HEADER_H + PAD // 2))
    
    # Outer thin border
    draw.rectangle([PAD - 4, HEADER_H + PAD // 2 - 4, PAD + photo_w + 4, HEADER_H + PAD // 2 + photo_h + 4], outline=(150, 140, 130), width=2)
    # Inner thin border
    draw.rectangle([PAD - 12, HEADER_H + PAD // 2 - 12, PAD + photo_w + 12, HEADER_H + PAD // 2 + photo_h + 12], outline=(150, 140, 130), width=1)
    
    # Title & Price in footer
    footer_y = HEADER_H + PHOTO_H
    tf = _get_font(int(FOOTER_H * 0.22), bold=True, serif=True)
    lines = _wrap_text(title, tf, PIN_W - PAD * 3 - (140 if price else 0))
    for i, line in enumerate(lines[:2]):
        draw.text((PAD, footer_y + int(FOOTER_H * 0.15) + i * int(FOOTER_H * 0.28)), line, fill=BLACK, font=tf)

    # Soft typewriter/handwritten price badge
    if price:
        pf = _get_font(int(FOOTER_H * 0.24), bold=False, serif=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+24, pb[3]-pb[1]+12
        px = PIN_W - PAD - pw
        py = footer_y + int(FOOTER_H * 0.15)
        draw.rectangle([px, py, px+pw, py+ph], fill=(235, 230, 225), outline=(180, 175, 170), width=1)
        draw.text((px+12, py+6), ps, fill=DARK_GREY, font=pf)

    # Sage/Earth tone CTA footer
    _draw_cta_bar(canvas, draw, footer_y + FOOTER_H, CTA_H, SAGE, WHITE)


# ── Template G ───────────────────────────────────────────────────────────────
# Glamoratti High-Drama Vogue: deep black/charcoal bg, elegant gold border,
# serif/sans bold caps.
def _template_g(draw, canvas, photo, title, category, price):
    draw.rectangle([(0, 0), (PIN_W, PIN_H)], fill=BLACK)

    HEADER_H = int(PIN_H * 0.12)
    CTA_H = int(PIN_H * 0.10)
    FOOTER_H = int(PIN_H * 0.22)
    PHOTO_H = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD = int(PIN_W * 0.06)

    # Large Photo
    photo_w = PIN_W - PAD * 2
    photo_h = PHOTO_H
    p = _boost(_fit_image(photo, photo_w, photo_h))
    canvas.paste(p, (PAD, HEADER_H))

    # Champagne gold/coral frame outline around photo
    draw.rectangle([PAD - 2, HEADER_H - 2, PAD + photo_w + 2, HEADER_H + photo_h + 2], outline=CORAL, width=3)

    # Header category uppercase spaced
    cf = _get_font(int(HEADER_H * 0.32), bold=True)
    spaced_cat = "  ".join(list(category.upper()))
    cb = cf.getbbox(spaced_cat)
    draw.text(((PIN_W - (cb[2]-cb[0])) // 2, int(HEADER_H * 0.35)), spaced_cat, fill=CORAL, font=cf)

    # Footer
    footer_y = HEADER_H + PHOTO_H
    tf = _get_font(int(FOOTER_H * 0.20), bold=True, serif=True)
    lines = _wrap_text(title.upper(), tf, PIN_W - PAD * 2)
    for i, line in enumerate(lines[:2]):
        draw.text((PAD, footer_y + int(FOOTER_H * 0.15) + i * int(FOOTER_H * 0.24)), line, fill=WHITE, font=tf)

    # Gold-colored price tag
    if price:
        pf = _get_font(int(FOOTER_H * 0.22), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        draw.text((PAD, footer_y + int(FOOTER_H * 0.65)), ps, fill=CORAL, font=pf)

    # Black CTA with gold/coral text
    _draw_cta_bar(canvas, draw, footer_y + FOOTER_H, CTA_H, BLACK, CORAL)


# ── Template H ───────────────────────────────────────────────────────────────
# Vamp Romantic Cinematic: moody vignettes, high-contrast serif typography.
def _template_h(draw, canvas, photo, title, category, price):
    CTA_H = int(PIN_H * 0.10)
    PHOTO_H = PIN_H - CTA_H

    # Full photo with 1.15x brightness reduction to look moody
    p = ImageEnhance.Brightness(_fit_image(photo, PIN_W, PHOTO_H)).enhance(0.85)
    p = ImageEnhance.Contrast(p).enhance(1.15)
    canvas.paste(p, (0, 0))

    # Deep vignette (dark corners and bottom)
    overlay = Image.new("RGBA", (PIN_W, PHOTO_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # Bottom gradient (heavy dark)
    bottom_h = int(PHOTO_H * 0.50)
    for y in range(bottom_h):
        alpha = int(230 * (y / bottom_h))
        od.rectangle([(0, PHOTO_H - bottom_h + y), (PIN_W, PHOTO_H - bottom_h + y)], fill=(12, 5, 15, alpha))
    # Top gradient (light dark)
    top_h = int(PHOTO_H * 0.20)
    for y in range(top_h):
        alpha = int(120 * (1.0 - (y / top_h)))
        od.rectangle([(0, y), (PIN_W, y)], fill=(12, 5, 15, alpha))

    canvas.paste(Image.alpha_composite(p.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(canvas)

    margin = int(PIN_W * 0.08)
    
    # Category (Spaced white serif uppercase)
    cf = _get_font(int(PIN_H * 0.026), bold=True, serif=True)
    draw.text((margin, int(PIN_H * 0.05)), category.upper(), fill=WHITE, font=cf)

    # Title bottom left (Modern elegant serif)
    tf = _get_font(int(PIN_H * 0.052), bold=True, serif=True)
    lines = _wrap_text(title, tf, PIN_W - margin * 2)
    start_y = PHOTO_H - int(PIN_H * 0.25)
    for i, line in enumerate(lines[:2]):
        draw.text((margin, start_y + i * int(PIN_H * 0.065)), line, fill=WHITE, font=tf)

    # Price bottom left below title
    if price:
        pf = _get_font(int(PIN_H * 0.045), bold=True, serif=True)
        draw.text((margin, PHOTO_H - int(PIN_H * 0.10)), f"${price}", fill=BLUSH, font=pf)

    # Charcoal CTA bar
    _draw_cta_bar(canvas, draw, PHOTO_H, CTA_H, (22, 12, 25), WHITE)


# ── Template I ───────────────────────────────────────────────────────────────
# Extra-Celestial Holographic: pastel/lavender gradient bg, floating photo,
# futuristic minimalist style.
def _template_i(draw, canvas, photo, title, category, price):
    # Pastel/mint/lavender gradient background
    gradient = Image.new("RGB", (PIN_W, PIN_H))
    gd = ImageDraw.Draw(gradient)
    for y in range(PIN_H):
        t = y / PIN_H
        # Mix from pale pink to soft lavender to mint green
        r = int(245 * (1-t) + 230 * t)
        g = int(230 * (1-t) + 242 * t)
        b = int(245 * (1-t) + 238 * t)
        gd.line([(0, y), (PIN_W, y)], fill=(r, g, b))
    canvas.paste(gradient, (0, 0))
    draw = ImageDraw.Draw(canvas)

    HEADER_H = int(PIN_H * 0.12)
    CTA_H = int(PIN_H * 0.10)
    FOOTER_H = int(PIN_H * 0.20)
    PHOTO_H = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD = int(PIN_W * 0.06)

    # Floating image with rounded corners and shadow
    photo_w = PIN_W - PAD * 2
    photo_h = PHOTO_H - PAD
    p = _boost(_fit_image(photo, photo_w, photo_h))
    
    # Shadow rect
    shadow = Image.new("RGBA", (photo_w, photo_h), (0, 0, 0, 45))
    canvas.paste(shadow, (PAD + 8, HEADER_H + PAD // 2 + 8))
    canvas.paste(p, (PAD, HEADER_H + PAD // 2))

    # Category floating in top-left
    cf = _get_font(int(HEADER_H * 0.30), bold=True)
    draw.text((PAD + 12, HEADER_H - int(HEADER_H * 0.10)), category.upper(), fill=DARK_GREY, font=cf)

    # Footer Title & Price
    footer_y = HEADER_H + PHOTO_H
    tf = _get_font(int(FOOTER_H * 0.20), bold=True)
    lines = _wrap_text(title, tf, PIN_W - PAD * 3 - (140 if price else 0))
    for i, line in enumerate(lines[:2]):
        draw.text((PAD, footer_y + int(FOOTER_H * 0.10) + i * int(FOOTER_H * 0.28)), line, fill=BLACK, font=tf)

    if price:
        pf = _get_font(int(FOOTER_H * 0.24), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+28, pb[3]-pb[1]+14
        px = PIN_W - PAD - pw
        py = footer_y + int(FOOTER_H * 0.10)
        _draw_rounded_rect(draw, (px, py, px+pw, py+ph), 14, BLACK)
        draw.text((px+14, py+7), ps, fill=WHITE, font=pf)

    # Neon blue/mint CTA footer
    _draw_cta_bar(canvas, draw, footer_y + FOOTER_H, CTA_H, NAVY, WHITE)


# ── Template J ───────────────────────────────────────────────────────────────
# Blog Article Editorial Template:
# Soft warm cream, large serif "MeeeShop Blog", thin elegant border, excerpt.
def _template_j(draw, canvas, photo, title, category, excerpt):
    bg_color = (250, 248, 245)
    draw.rectangle([(0, 0), (PIN_W, PIN_H)], fill=bg_color)

    HEADER_H = int(PIN_H * 0.18)
    CTA_H = int(PIN_H * 0.10)
    FOOTER_H = int(PIN_H * 0.24)
    PHOTO_H = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD = int(PIN_W * 0.08)

    # Blog Header Title
    blog_header = category or "MeeeShop Blog"
    cf = _get_font(int(HEADER_H * 0.25), bold=True, serif=True)
    cb = cf.getbbox(blog_header)
    draw.text(((PIN_W - (cb[2]-cb[0])) // 2, int(HEADER_H * 0.28)), blog_header, fill=BLACK, font=cf)
    
    # Elegant divider line
    draw.line([(PAD, int(HEADER_H * 0.65)), (PIN_W - PAD, int(HEADER_H * 0.65))], fill=MID_GREY, width=1)

    # Photo centered with double thin borders
    photo_w = PIN_W - PAD * 2
    photo_h = PHOTO_H - PAD
    p = _boost(_fit_image(photo, photo_w, photo_h))
    canvas.paste(p, (PAD, HEADER_H + PAD // 2))
    
    # Outer thin border
    draw.rectangle([PAD - 4, HEADER_H + PAD // 2 - 4, PAD + photo_w + 4, HEADER_H + PAD // 2 + photo_h + 4], outline=MID_GREY, width=1)

    # Footer Title & Excerpt
    footer_y = HEADER_H + PHOTO_H
    tf = _get_font(int(FOOTER_H * 0.15), bold=True, serif=True)
    lines = _wrap_text(title, tf, PIN_W - PAD * 2)
    for i, line in enumerate(lines[:2]):
        draw.text((PAD, footer_y + int(FOOTER_H * 0.10) + i * int(FOOTER_H * 0.20)), line, fill=BLACK, font=tf)

    # Blog excerpt/description preview (regular serif, smaller)
    ef = _get_font(int(FOOTER_H * 0.09), bold=False, serif=True)
    clean_excerpt = excerpt or "Read our latest article for styling tips, outfits, and fashion trends..."
    excerpt_lines = _wrap_text(clean_excerpt, ef, PIN_W - PAD * 2)
    for i, line in enumerate(excerpt_lines[:2]):
        draw.text((PAD, footer_y + int(FOOTER_H * 0.54) + i * int(FOOTER_H * 0.13)), line, fill=DARK_GREY, font=ef)

    # Elegant Burgundy/Red CTA Footer
    draw.rectangle([(0, footer_y + FOOTER_H), (PIN_W, footer_y + FOOTER_H + CTA_H)], fill=(115, 30, 70))
    margin = int(PIN_W * 0.05)
    font, cta_text = _fit_text("READ THE BLOG POST →", bold=True, max_w=PIN_W - 2 * margin, start_size=int(CTA_H * 0.35))
    tb = font.getbbox(cta_text)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    draw.text(((PIN_W - tw) // 2, footer_y + FOOTER_H + (CTA_H - th) // 2), cta_text, fill=WHITE, font=font)


# ── Template K ───────────────────────────────────────────────────────────────
# 2-Image vertical split collage: Left side is photo, right side is photo2.
# Soft aesthetic linen background, elegant serif title and price tag at the bottom.
def _template_k(draw, canvas, photo, photo2, title, category, price):
    bg_color = (248, 245, 240)
    draw.rectangle([(0, 0), (PIN_W, PIN_H)], fill=bg_color)

    HEADER_H = int(PIN_H * 0.12)
    CTA_H = int(PIN_H * 0.10)
    FOOTER_H = int(PIN_H * 0.20)
    PHOTO_H = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD = int(PIN_W * 0.05)

    # Category top centered (spaced, elegant sans-serif)
    cf = _get_font(int(HEADER_H * 0.32), bold=True)
    spaced_cat = "  ".join(list(category.upper()))
    cb = cf.getbbox(spaced_cat)
    draw.text(((PIN_W - (cb[2]-cb[0])) // 2, int(HEADER_H * 0.35)), spaced_cat, fill=DARK_GREY, font=cf)

    # Calculate widths for 2 photos
    photo_w = (PIN_W - PAD * 3) // 2
    photo_h = PHOTO_H

    # Left Photo
    p1 = _boost(_fit_image(photo, photo_w, photo_h))
    canvas.paste(p1, (PAD, HEADER_H))

    # Right Photo (fallback to same photo if photo2 is none)
    img2 = photo2 if photo2 else photo
    p2 = _boost(_fit_image(img2, photo_w, photo_h))
    canvas.paste(p2, (PAD * 2 + photo_w, HEADER_H))

    # Draw thin borders around both
    draw.rectangle([PAD, HEADER_H, PAD + photo_w, HEADER_H + photo_h], outline=(200, 195, 185), width=2)
    draw.rectangle([PAD * 2 + photo_w, HEADER_H, PAD * 2 + photo_w * 2, HEADER_H + photo_h], outline=(200, 195, 185), width=2)

    # Footer Title & Price
    footer_y = HEADER_H + PHOTO_H
    tf = _get_font(int(FOOTER_H * 0.20), bold=True, serif=True)
    lines = _wrap_text(title, tf, PIN_W - PAD * 3 - (140 if price else 0))
    for i, line in enumerate(lines[:2]):
        draw.text((PAD, footer_y + int(FOOTER_H * 0.15) + i * int(FOOTER_H * 0.28)), line, fill=BLACK, font=tf)

    if price:
        pf = _get_font(int(FOOTER_H * 0.24), bold=True, serif=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        pw, ph = pb[2]-pb[0]+24, pb[3]-pb[1]+12
        px = PIN_W - PAD - pw
        py = footer_y + int(FOOTER_H * 0.15)
        draw.rectangle([px, py, px+pw, py+ph], fill=(235, 230, 225), outline=(180, 175, 170), width=1)
        draw.text((px+12, py+6), ps, fill=DARK_GREY, font=pf)

    # Soft Rose CTA
    _draw_cta_bar(canvas, draw, footer_y + FOOTER_H, CTA_H, (188, 108, 37), WHITE)


# ── Template L ───────────────────────────────────────────────────────────────
# 3-Image lifestyle grid: 1 large main image top, 2 smaller images bottom.
# Dark chic background for high contrast.
def _template_l(draw, canvas, photo, photo2, photo3, title, category, price):
    bg_color = (25, 25, 28)
    draw.rectangle([(0, 0), (PIN_W, PIN_H)], fill=bg_color)

    HEADER_H = int(PIN_H * 0.10)
    CTA_H = int(PIN_H * 0.10)
    FOOTER_H = int(PIN_H * 0.20)
    PHOTO_H = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD = int(PIN_W * 0.04)

    # Category top left
    cf = _get_font(int(HEADER_H * 0.35), bold=True)
    draw.text((PAD, int(HEADER_H * 0.35)), category.upper(), fill=CORAL, font=cf)

    # Main Image Top (PHOTO_H * 0.55)
    top_h = int(PHOTO_H * 0.55)
    p_top = _boost(_fit_image(photo, PIN_W - PAD * 2, top_h))
    canvas.paste(p_top, (PAD, HEADER_H))

    # Bottom 2 Images (PHOTO_H * 0.40)
    bottom_h = PHOTO_H - top_h - PAD
    sub_w = (PIN_W - PAD * 3) // 2

    img2 = photo2 if photo2 else photo
    img3 = photo3 if photo3 else (photo2 if photo2 else photo)

    p_bottom_left = _boost(_fit_image(img2, sub_w, bottom_h))
    p_bottom_right = _boost(_fit_image(img3, sub_w, bottom_h))

    canvas.paste(p_bottom_left, (PAD, HEADER_H + top_h + PAD))
    canvas.paste(p_bottom_right, (PAD * 2 + sub_w, HEADER_H + top_h + PAD))

    # Footer Info
    footer_y = HEADER_H + PHOTO_H
    tf = _get_font(int(FOOTER_H * 0.18), bold=True)
    lines = _wrap_text(title, tf, PIN_W - PAD * 3 - (140 if price else 0))
    for i, line in enumerate(lines[:2]):
        draw.text((PAD, footer_y + int(FOOTER_H * 0.15) + i * int(FOOTER_H * 0.28)), line, fill=WHITE, font=tf)

    if price:
        pf = _get_font(int(FOOTER_H * 0.24), bold=True)
        draw.text((PIN_W - PAD - 120, footer_y + int(FOOTER_H * 0.15)), f"${price}", fill=CORAL, font=pf)

    # Coral CTA Bar
    _draw_cta_bar(canvas, draw, footer_y + FOOTER_H, CTA_H, CORAL, WHITE)


# ── Template M ───────────────────────────────────────────────────────────────
# Clean Polaroid style with negative space and linen background.
# Minimalist, elegant serif text caption underneath.
def _template_m(draw, canvas, photo, title, category, price):
    bg_color = (245, 242, 237)
    draw.rectangle([(0, 0), (PIN_W, PIN_H)], fill=bg_color)

    HEADER_H = int(PIN_H * 0.08)
    CTA_H = int(PIN_H * 0.10)
    FOOTER_H = int(PIN_H * 0.26)
    PHOTO_H = PIN_H - HEADER_H - FOOTER_H - CTA_H
    PAD = int(PIN_W * 0.10)

    # Category small and light
    cf = _get_font(int(HEADER_H * 0.35), bold=False, serif=True)
    cb = cf.getbbox(category)
    draw.text(((PIN_W - (cb[2]-cb[0])) // 2, int(HEADER_H * 0.30)), category.upper(), fill=MID_GREY, font=cf)

    # Polaroid style photo frame
    photo_w = PIN_W - PAD * 2
    photo_h = PHOTO_H
    p = _boost(_fit_image(photo, photo_w, photo_h))
    
    # White background card
    draw.rectangle([PAD - 12, HEADER_H - 12, PAD + photo_w + 12, HEADER_H + photo_h + 30], fill=WHITE)
    # Paste photo
    canvas.paste(p, (PAD, HEADER_H))
    # Soft outline around the photo
    draw.rectangle([PAD, HEADER_H, PAD + photo_w, HEADER_H + photo_h], outline=(230, 225, 220), width=1)
    
    # Title & Price in Polaroid footer area
    footer_y = HEADER_H + PHOTO_H + 40
    tf = _get_font(int(FOOTER_H * 0.15), bold=False, serif=True)
    lines = _wrap_text(title, tf, PIN_W - PAD * 3 - (140 if price else 0))
    for i, line in enumerate(lines[:2]):
        lb = tf.getbbox(line)
        lx = (PIN_W - (lb[2]-lb[0])) // 2
        draw.text((lx, footer_y + i * int(FOOTER_H * 0.20)), line, fill=DARK_GREY, font=tf)

    if price:
        pf = _get_font(int(FOOTER_H * 0.18), bold=True, serif=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        px = (PIN_W - (pb[2]-pb[0])) // 2
        py = footer_y + len(lines[:2]) * int(FOOTER_H * 0.20) + 10
        draw.text((px, py), ps, fill=RED, font=pf)

    # Minimalist dark olive/sage CTA footer
    _draw_cta_bar(canvas, draw, PIN_H - CTA_H, CTA_H, (60, 75, 65), WHITE)


# ── Template N ───────────────────────────────────────────────────────────────
# Direct image with transparent overlay text in the center
def _template_n(draw, canvas, photo, title, category, price):
    # Full bleed photo
    p = _boost(_fit_image(photo, PIN_W, PIN_H))
    canvas.paste(p, (0, 0))

    # Transparent center overlay for text
    overlay = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    
    # Box dimensions
    box_w = int(PIN_W * 0.85)
    box_h = int(PIN_H * 0.35)
    box_x = (PIN_W - box_w) // 2
    box_y = (PIN_H - box_h) // 2

    # Draw semi-transparent black rectangle
    od.rounded_rectangle([box_x, box_y, box_x + box_w, box_y + box_h], radius=20, fill=(0, 0, 0, 160))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(canvas)

    # Text inside
    margin = int(box_w * 0.05)
    cf = _get_font(int(box_h * 0.12), bold=True)
    cb = cf.getbbox(category.upper())
    draw.text(((PIN_W - (cb[2]-cb[0])) // 2, box_y + int(box_h * 0.1)), category.upper(), fill=WHITE, font=cf)

    tf = _get_font(int(box_h * 0.20), bold=True)
    lines = _wrap_text(title, tf, box_w - 2*margin)
    for i, line in enumerate(lines[:2]):
        lb = tf.getbbox(line)
        draw.text(((PIN_W - (lb[2]-lb[0])) // 2, box_y + int(box_h * 0.35) + i * int(box_h * 0.25)), line, fill=WHITE, font=tf)

    if price:
        pf = _get_font(int(box_h * 0.18), bold=True)
        ps = f"${price}"
        pb = pf.getbbox(ps)
        draw.text(((PIN_W - (pb[2]-pb[0])) // 2, box_y + int(box_h * 0.8)), ps, fill=CORAL, font=pf)


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
) -> Optional[str]:
    """
    Create a Pinterest pin using one of 12 rotating Kohl's-style/aesthetic templates
    or template 9 for Blog Editorial posts. Matches aesthetic templates to boards.
    """
    try:
        ecommerce_templates = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12]
        
        # Smart template matching based on board name
        b_lower = board_name.lower()
        if template_index is None:
            if "poetcore" in b_lower:
                template_index = 5  # Poetcore Storybook Editorial
            elif "vamp" in b_lower or "romantic" in b_lower:
                template_index = 7  # Vamp Romantic Cinematic
            elif "gummy" in b_lower or "nostalgia" in b_lower:
                template_index = 8  # Holographic
            elif "athlete" in b_lower or "off-duty" in b_lower:
                template_index = 10 # Split collage
            elif "blog" in b_lower:
                template_index = 9
            else:
                template_index = 13 # Template N: Center transparent overlay

        canvas = Image.new("RGB", (PIN_W, PIN_H), WARM_WHITE)
        draw = ImageDraw.Draw(canvas)

        if Path(product_image_path).exists():
            photo = Image.open(product_image_path).convert("RGB")
        else:
            photo = Image.new("RGB", (PIN_W, PIN_H), (200, 200, 200))
            logger.warning(f"Product image not found: {product_image_path}")

        photo2 = None
        photo3 = None
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
            _template_j(draw, canvas, photo, title, category, price)
        elif template_index == 10:
            _template_k(draw, canvas, photo, photo2, title, category, price)
        elif template_index == 11:
            _template_l(draw, canvas, photo, photo2, photo3, title, category, price)
        elif template_index == 12:
            _template_m(draw, canvas, photo, title, category, price)
        elif template_index == 13:
            _template_n(draw, canvas, photo, title, category, price)
        else:
            _template_n(draw, canvas, photo, title, category, price)

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
    additional_image_paths: Optional[List[str]] = None,
    board_name: str = "",
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
        additional_image_paths=additional_image_paths,
        board_name=board_name,
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
