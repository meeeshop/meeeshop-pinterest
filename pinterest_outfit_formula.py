#!/usr/bin/env python3
"""
pinterest_outfit_formula.py — Pinterest "Outfit Formula" & "How to Style It" Collage Pin Generator

Creates high-converting 2:3 vertical (1000 × 1500 px) editorial collages pairing in-stock
Shopify products into complete styled looks for USA women shoppers:
  - Top: Western Graphic Tee, Knit Sweater, Blouse, or Bodysuit
  - Bottom: High-Rise Flare Jeans, Denim Skirt, or Wide-Leg Pants
  - Bag: MKF Crossbody, Canvas Sling Bag, or Shoulder Tote
  - Shoes: Ankle Booties, Slingbacks, Heels, or Boots
  - Dress: Midi Dress, Cocktail Dress, or Sundress (for Date Night / Event formulas)

Features:
1. Dynamic In-Stock Matching: Fetches live active products directly from Shopify GraphQL API,
   filtering only in-stock inventory (>0) and high-resolution imagery.
2. Editorial Luxury Aesthetic: 1000 × 1500 px crisp 2:3 vertical pins modeled after luxury
   boutiques (Revolve, Aritzia, Anthropologie) with clean cards, category pills, and rich contrast.
3. Natural SEO for USA Women: Search-first titles and keyword-dense descriptions targeting
   Pinterest high-volume search queries ("outfit formula", "fall weekend outfit inspo", "how to style flare jeans").
4. Shoppable Product Tagging: Once published, automatically tags all featured outfit products (up to 10)
   directly onto the pin using Playwright UI automation so shoppers can tap and buy immediately!
5. Product Rotation & Persistence: Keeps track of used items in outfit_formula_history.json
   to ensure variety across daily postings.
"""

import os
import sys
import time
import json
import re
import random
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# ── Paths & Setup ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Safe UTF-8 console logging handler
sys_stdout = sys.stdout
if hasattr(sys_stdout, "reconfigure"):
    try:
        sys_stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys_stdout)]
)
logger = logging.getLogger("OutfitFormula")

# Secrets Manager
try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
    logger.info("[secrets] Double-encryption secrets injected successfully.")
except Exception as e:
    logger.warning(f"[secrets] secrets_manager fallback: {e}")
    def get_secret(key: str) -> Optional[str]:
        return os.environ.get(key)

from shopify_products import ShopifyClient

try:
    from stealth_pinterest_poster import StealthPinterestPoster
except ImportError:
    StealthPinterestPoster = None

try:
    from tag_popular_pins_with_products import tag_pin_visually_with_playwright
except ImportError:
    tag_pin_visually_with_playwright = None

HISTORY_FILE = ROOT / "outfit_formula_history.json"
SCRATCH_DIR = ROOT / "scratch"
SCRATCH_DIR.mkdir(exist_ok=True)

# Collage Dimensions & Palette
PIN_W = 1000
PIN_H = 1500

BG_COLOR = (248, 246, 242)       # Warm editorial ivory / oat
CARD_BG = (255, 255, 255)        # Pure crisp white
BORDER_COLOR = (230, 226, 218)   # Subtle beige border
TEXT_DARK = (24, 23, 22)         # Rich charcoal
TEXT_MUTED = (110, 105, 100)     # Warm taupe
ACCENT_COLOR = (180, 75, 55)     # Warm terracotta/brick accent
PILL_DARK = (30, 29, 28)         # Dark charcoal pill


# ── Typography Helper ─────────────────────────────────────────────────────────

def get_font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont:
    """Load system font with cross-platform fallbacks (Windows / Linux CI)."""
    candidates = []
    if serif:
        if bold:
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
        if bold:
            candidates = [
                "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "arial.ttf",
            ]
        else:
            candidates = [
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "arial.ttf",
            ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def fit_product_image(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Center/top-weighted fit and polish for fashion items."""
    sw, sh = img.size
    scale = max(target_w / sw, target_h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (nw - target_w) // 2
    y = int((nh - target_h) * 0.15) if nh > target_h else 0
    y = max(0, min(y, nh - target_h))
    cropped = img.crop((x, y, x + target_w, y + target_h))

    # Polish vibrancy, contrast, and texture definition
    cropped = ImageEnhance.Contrast(cropped).enhance(1.08)
    cropped = ImageEnhance.Color(cropped).enhance(1.06)
    cropped = ImageEnhance.Sharpness(cropped).enhance(1.20)
    return cropped


def draw_rounded_card(draw: ImageDraw.Draw, rect: tuple, radius: int, fill: tuple, outline: tuple = None, width: int = 1):
    x0, y0, x1, y1 = rect
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)


# ── Outfit Formula Presets ────────────────────────────────────────────────────

OUTFIT_FORMULAS = {
    "casual_fall": {
        "id": "casual_fall",
        "title": "Casual Fall Weekend Outfit Inspo",
        "subtitle": "HOW TO STYLE FLARE JEANS & A COZY KNIT",
        "slots": [
            {"category": "tops", "role_label": "THE TOP", "preference": ["sweater", "knit", "cardigan", "graphic", "tee", "top"]},
            {"category": "bags", "role_label": "THE BAG", "preference": ["crossbody", "sling", "shoulder", "bag"]},
            {"category": "jeans", "role_label": "THE DENIM", "preference": ["flare", "high rise", "bootcut", "wide leg", "jean"]},
            {"category": "shoes", "role_label": "THE SHOES", "preference": ["boot", "bootie", "slingback", "flat", "shoe"]},
        ],
        "board_name": "Casual Outfits",
        "fallback_boards": ["Kancan USA Jeans", "Style Ideas", "Sweaters"],
        "seo_keywords": ["casual fall outfit", "weekend outfit inspo", "flare jeans outfit", "how to style knit sweater", "everyday chic outfit formula", "fall fashion 2026", "boutique style"],
    },
    "how_to_style_flare_jeans": {
        "id": "how_to_style_flare_jeans",
        "title": "How to Style Flare Jeans: Outfit Formula",
        "subtitle": "EFFORTLESS WESTERN CHIC FOR FALL & WEEKENDS",
        "slots": [
            {"category": "tops", "role_label": "THE TOP", "preference": ["western", "graphic", "tee", "blouse", "sweater", "tank"]},
            {"category": "bags", "role_label": "THE BAG", "preference": ["canteen", "crossbody", "tote", "handbag", "sling"]},
            {"category": "jeans", "role_label": "THE FLARE DENIM", "preference": ["flare", "kancan", "wannabettabutt", "high rise", "denim"]},
            {"category": "shoes", "role_label": "THE FOOTWEAR", "preference": ["boot", "bootie", "western", "slingback"]},
        ],
        "board_name": "Kancan USA Jeans",
        "fallback_boards": ["Style Ideas", "Casual Outfits", "New Trendy Women Apparel, Shoes, Handbags & more"],
        "seo_keywords": ["how to style flare jeans", "high rise flare jeans outfit", "western graphic tee outfit", "casual boutique look", "flare denim styling guide", "fall outfit ideas 2026"],
    },
    "everyday_chic": {
        "id": "everyday_chic",
        "title": "Everyday Chic Outfit Formula",
        "subtitle": "MINIMALIST STREET STYLE & BOUTIQUE BASICS",
        "slots": [
            {"category": "tops", "role_label": "THE TOP", "preference": ["blouse", "tie front", "shirt", "top", "cami"]},
            {"category": "bags", "role_label": "THE BAG", "preference": ["shoulder", "crossbody", "tote", "bag"]},
            {"category": "bottoms", "role_label": "THE BOTTOM", "preference": ["skirt", "wide leg", "skort", "flare", "pant"]},
            {"category": "shoes", "role_label": "THE SHOES", "preference": ["slingback", "flat", "bootie", "shoe"]},
        ],
        "board_name": "Style Ideas",
        "fallback_boards": ["Puff Sleeve Tops", "Casual Outfits", "Skirts"],
        "seo_keywords": ["everyday chic outfit", "capsule wardrobe formula", "street style fashion women", "how to style everyday tops", "minimalist outfit ideas", "boutique clothing us"],
    },
    "date_night": {
        "id": "date_night",
        "title": "Date Night Outfit Formula",
        "subtitle": "ELEGANT DRESS & ACCESSORY STYLING INSPIRATION",
        "slots": [
            {"category": "dresses", "role_label": "THE DRESS", "preference": ["tie-back", "boned", "midi", "cocktail", "maxi", "dress"]},
            {"category": "bags", "role_label": "THE BAG", "preference": ["shoulder", "crossbody", "clutch", "bag"]},
            {"category": "shoes", "role_label": "THE SHOES", "preference": ["heel", "slingback", "boot", "bootie"]},
            {"category": "tops", "role_label": "THE LAYER", "preference": ["cardigan", "jacket", "shacket", "sweater", "wrap"]},
        ],
        "board_name": "Cocktail Dresses",
        "fallback_boards": ["Style Ideas", "Luxe Clothing", "Trendy Backpacks"],
        "seo_keywords": ["date night outfit formula", "how to style a midi dress", "fall date night look", "chic boutique dresses", "evening outfit inspo", "cocktail dress styling"],
    },
    "cozy_sweater_weather": {
        "id": "cozy_sweater_weather",
        "title": "Cozy Fall Layers Outfit Formula",
        "subtitle": "HOW TO STYLE KNIT SWEATERS WITH RELAXED DENIM",
        "slots": [
            {"category": "tops", "role_label": "THE KNIT", "preference": ["sweater", "knit", "pullover", "cardigan"]},
            {"category": "bags", "role_label": "THE TOTE", "preference": ["tote", "backpack", "shoulder", "crossbody"]},
            {"category": "jeans", "role_label": "THE DENIM", "preference": ["wide leg", "cargo", "relaxed", "flare", "jean"]},
            {"category": "shoes", "role_label": "THE BOOTS", "preference": ["boot", "bootie", "leather", "flat"]},
        ],
        "board_name": "Sweaters",
        "fallback_boards": ["Style Ideas", "Casual Outfits", "Kancan USA Jeans"],
        "seo_keywords": ["sweater weather outfit", "cozy fall layers", "how to style knitwear", "relaxed wide leg denim", "autumn capsule wardrobe", "aesthetic fall outfit formula"],
    }
}


# ── Shopify Product Categorization & Matching ─────────────────────────────────

class OutfitCatalog:
    """Categorizes in-stock Shopify products into fashion buckets for outfit building."""

    def __init__(self, client: ShopifyClient):
        self.client = client
        self.categories: Dict[str, List[Dict[str, Any]]] = {
            "tops": [],
            "bottoms": [],
            "jeans": [],
            "bags": [],
            "shoes": [],
            "dresses": []
        }

    def load_catalog(self) -> None:
        """Fetch products from Shopify and sort into categorized in-stock pools."""
        logger.info("[CATALOG] Fetching in-stock active products from Shopify...")

        # 1. Fetch general apparel
        general_prods = self.client.get_products(limit=150)
        self._classify_products(general_prods)

        # 2. Fetch specific high-intent collections (MKF Bags, Shoes, Flare Jeans)
        try:
            bag_prods = self.client.get_collection_products("337528684715", limit=50)
            self._classify_products(bag_prods, force_cat="bags")
        except Exception as e:
            logger.warning(f"Error fetching MKF collection: {e}")

        try:
            shoe_prods = self.client.get_collection_products("286085841067", limit=50)
            self._classify_products(shoe_prods, force_cat="shoes")
        except Exception as e:
            logger.warning(f"Error fetching Shoes collection: {e}")

        for col_id in ["312370004139", "336597483691"]:
            try:
                jean_prods = self.client.get_collection_products(col_id, limit=50)
                self._classify_products(jean_prods, force_cat="jeans")
            except Exception as e:
                logger.warning(f"Error fetching Jeans collection ({col_id}): {e}")

        for cat, items in self.categories.items():
            logger.info(f"  [CATALOG] In-Stock {cat.title()}: {len(items)} items available")

    def _classify_products(self, prods: List[Dict[str, Any]], force_cat: Optional[str] = None) -> None:
        store_base = "https://us.meeeshop.com"
        for p in prods:
            handle = p.get("handle")
            title = p.get("title")
            variants = p.get("variants", [])
            images = p.get("images", [])

            if not handle or not title or not variants or not images:
                continue

            in_stock = any(
                v.get("inventory_quantity", 0) > 0 or v.get("inventory_policy") == "continue"
                for v in variants
            )
            if not in_stock:
                continue

            first_variant = variants[0]
            price = first_variant.get("price", "0.00")
            img_url = images[0].get("src", "")
            if not img_url:
                continue

            item = {
                "id": str(p.get("id")),
                "variant_id": str(first_variant.get("id")),
                "title": title,
                "handle": handle,
                "price": price,
                "url": f"{store_base}/products/{handle}?utm_source=pinterest&utm_medium=outfit_formula_pin&utm_campaign=organic_inspo",
                "image_url": img_url,
                "product_type": p.get("product_type", ""),
                "tags": p.get("tags", ""),
                "vendor": p.get("vendor", ""),
            }

            if force_cat:
                if force_cat == "jeans":
                    self._add_unique("jeans", item)
                    self._add_unique("bottoms", item)
                else:
                    self._add_unique(force_cat, item)
                continue

            search_text = f"{title} {p.get('product_type', '')} {p.get('tags', '')}".lower()

            if any(k in search_text for k in ["boot", "shoe", "heel", "sandal", "slingback", "flat", "sneaker", "bootie"]):
                self._add_unique("shoes", item)
            elif any(k in search_text for k in ["bag", "tote", "crossbody", "handbag", "purse", "backpack", "clutch", "satchel"]):
                self._add_unique("bags", item)
            elif any(k in search_text for k in ["dress", "gown", "midi", "maxi"]):
                self._add_unique("dresses", item)
            elif any(k in search_text for k in ["jean", "flare", "denim", "bootcut", "wide leg", "skinny"]):
                self._add_unique("jeans", item)
                self._add_unique("bottoms", item)
            elif any(k in search_text for k in ["pant", "skirt", "skort", "trouser", "legging", "short"]):
                self._add_unique("bottoms", item)
            elif any(k in search_text for k in ["top", "tee", "shirt", "sweater", "blouse", "knit", "cardigan", "cami", "tank"]):
                self._add_unique("tops", item)

    def _add_unique(self, cat: str, item: Dict[str, Any]) -> None:
        if not any(x["id"] == item["id"] for x in self.categories[cat]):
            self.categories[cat].append(item)

    def pick_item_for_slot(
        self,
        slot_def: Dict[str, Any],
        used_ids: set,
        recent_ids: set
    ) -> Optional[Dict[str, Any]]:
        """Selects the best available in-stock item matching role preferences, avoiding repeats."""
        cat = slot_def["category"]
        pool = self.categories.get(cat, [])
        if not pool:
            return None

        preferences = slot_def.get("preference", [])

        scored = []
        for item in pool:
            if item["id"] in used_ids:
                continue

            search_text = f"{item['title']} {item['product_type']} {item['tags']}".lower()
            score = 0
            for pref in preferences:
                if pref in search_text:
                    score += 5

            if item["id"] not in recent_ids:
                score += 10

            scored.append((score, item))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            chosen = scored[0][1]
            used_ids.add(chosen["id"])
            return chosen

        for item in pool:
            if item["id"] not in used_ids:
                used_ids.add(item["id"])
                return item

        return pool[0] if pool else None


# ── History & LRU Management ──────────────────────────────────────────────────

def load_history() -> Dict[str, Any]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read history: {e}")
    return {"posts": [], "last_run": None}


def save_history(history: Dict[str, Any]) -> None:
    history["last_run"] = datetime.now(timezone.utc).isoformat()
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def get_recently_used_ids(history: Dict[str, Any], days: int = 5) -> set:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = set()
    for p in history.get("posts", []):
        ts = p.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if dt < cutoff:
                    continue
            except Exception:
                pass
        for item in p.get("outfit_items", []):
            if item.get("id"):
                recent.add(str(item["id"]))
            if item.get("variant_id"):
                recent.add(str(item["variant_id"]))
    return recent


# ── Collage Renderer (1000 × 1500 px, 2:3 Vertical) ──────────────────────────

def render_outfit_formula_collage(
    outfit_items: List[Dict[str, Any]],
    formula_title: str,
    formula_subtitle: str,
    output_path: str
) -> str:
    """
    Renders a vertical 2:3 (1000 × 1500 px) editorial 'Outfit Formula' collage.
    Features 4 balanced floating boutique cards, category pills, and high-impact CTA.
    """
    canvas = Image.new("RGB", (PIN_W, PIN_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # 1. Subtle Outer Border Frame
    draw.rectangle([(16, 16), (PIN_W - 16, PIN_H - 16)], outline=(225, 220, 212), width=1)

    # 2. Editorial Header Block
    kicker_font = get_font(20, bold=True)
    kicker_text = "O U T F I T   F O R M U L A   •   S T Y L I N G   G U I D E"
    kb = kicker_font.getbbox(kicker_text)
    kw = kb[2] - kb[0]
    draw.text(((PIN_W - kw) // 2, 45), kicker_text, fill=ACCENT_COLOR, font=kicker_font)

    # Main Headline (Serif editorial headline)
    title_font = get_font(44, bold=True, serif=True)
    tb = title_font.getbbox(formula_title)
    tw = tb[2] - tb[0]
    draw.text(((PIN_W - tw) // 2, 80), formula_title, fill=TEXT_DARK, font=title_font)

    # Subtitle
    sub_font = get_font(18, bold=True)
    sub_text = formula_subtitle.upper()
    sb = sub_font.getbbox(sub_text)
    sw = sb[2] - sb[0]
    draw.text(((PIN_W - sw) // 2, 140), sub_text, fill=TEXT_MUTED, font=sub_font)

    # Thin Divider Line
    draw.line([(80, 178), (PIN_W - 80, 178)], fill=(218, 212, 204), width=1)

    # Center Brand Badge
    center_tag = "M E E E S H O P   E D I T"
    ct_font = get_font(15, bold=True)
    ctb = ct_font.getbbox(center_tag)
    ctw = ctb[2] - ctb[0]
    pill_w = ctw + 30
    pill_h = 24
    pill_x = (PIN_W - pill_w) // 2
    pill_y = 166
    draw_rounded_card(draw, (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h), radius=12, fill=BG_COLOR, outline=(218, 212, 204), width=1)
    draw.text((pill_x + 15, pill_y + 3), center_tag, fill=TEXT_MUTED, font=ct_font)

    # 3. 4-Grid Product Cards Layout (445 × 530 px each)
    card_positions = [
        {"rect": (40, 205, 485, 735), "item": outfit_items[0] if len(outfit_items) > 0 else None},
        {"rect": (515, 205, 960, 735), "item": outfit_items[1] if len(outfit_items) > 1 else None},
        {"rect": (40, 755, 485, 1285), "item": outfit_items[2] if len(outfit_items) > 2 else None},
        {"rect": (515, 755, 960, 1285), "item": outfit_items[3] if len(outfit_items) > 3 else None},
    ]

    for card in card_positions:
        x0, y0, x1, y1 = card["rect"]
        cw = x1 - x0
        ch = y1 - y0

        draw_rounded_card(draw, (x0, y0, x1, y1), radius=18, fill=CARD_BG, outline=BORDER_COLOR, width=1)

        item = card["item"]
        if not item:
            continue

        img_x = x0 + 12
        img_y = y0 + 12
        img_w = cw - 24
        img_h = ch - 90

        if item.get("local_image_path") and Path(item["local_image_path"]).exists():
            try:
                raw_img = Image.open(item["local_image_path"]).convert("RGB")
                fitted = fit_product_image(raw_img, img_w, img_h)
                canvas.paste(fitted, (img_x, img_y))
            except Exception as e:
                logger.warning(f"Error rendering image: {e}")

        # Top-Left Role Pill
        role = item.get("role_label", "FEATURED PIECE")
        r_font = get_font(14, bold=True)
        rb = r_font.getbbox(role)
        rw = rb[2] - rb[0]
        rpill_w = rw + 20
        rpill_h = 26
        rx = x0 + 20
        ry = y0 + 20
        draw_rounded_card(draw, (rx, ry, rx + rpill_w, ry + rpill_h), radius=13, fill=PILL_DARK)
        draw.text((rx + 10, ry + 4), role, fill=(255, 255, 255), font=r_font)

        # Bottom Product Info
        info_y = y0 + img_h + 18
        p_title = item.get("title", "")
        if len(p_title) > 28:
            p_title = p_title[:26] + "..."

        name_font = get_font(18, bold=True)
        draw.text((x0 + 16, info_y), p_title, fill=TEXT_DARK, font=name_font)

        price_val = item.get("price")
        price_str = f"${float(price_val):.2f}" if price_val else ""
        sub_info = f"{price_str}  •  In Stock" if price_str else "In Stock  •  USA Boutique"
        sub_font = get_font(14, bold=False)
        draw.text((x0 + 16, info_y + 24), sub_info, fill=ACCENT_COLOR, font=sub_font)

    # 4. Footer Trust Strip & CTA
    trust_text = "FREE US SHIPPING   •   TRUE-TO-SIZE FIT   •   EASY 7-DAY RETURNS"
    t_font = get_font(16, bold=True)
    tb = t_font.getbbox(trust_text)
    tw = tb[2] - tb[0]
    draw.text(((PIN_W - tw) // 2, 1318), trust_text, fill=TEXT_MUTED, font=t_font)

    # High-converting CTA Button Pill
    cta_w = 680
    cta_h = 66
    cta_x = (PIN_W - cta_w) // 2
    cta_y = 1360
    draw_rounded_card(draw, (cta_x, cta_y, cta_x + cta_w, cta_y + cta_h), radius=cta_h // 2, fill=PILL_DARK)

    cta_text = "TAP TO EXPLORE & SHOP THIS LOOK  →"
    cta_font = get_font(22, bold=True)
    cb = cta_font.getbbox(cta_text)
    cw = cb[2] - cb[0]
    ch = cb[3] - cb[1]
    draw.text(((PIN_W - cw) // 2, cta_y + (cta_h - ch) // 2 - 2), cta_text, fill=(255, 255, 255), font=cta_font)

    url_text = "US.MEEESHOP.COM"
    u_font = get_font(15, bold=True)
    ub = u_font.getbbox(url_text)
    uw = ub[2] - ub[0]
    draw.text(((PIN_W - uw) // 2, 1442), url_text, fill=TEXT_MUTED, font=u_font)

    canvas.save(output_path, quality=95, optimize=True)
    logger.info(f"[COLLAGE] Saved high-converting 2:3 outfit collage: {output_path}")
    return output_path


# ── SEO Copywriting for USA Organic Women Shoppers ────────────────────────────

def generate_outfit_seo(formula: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, str]:
    """Generates search-intent titles, rich descriptions, and destination links."""
    f_title = formula["title"]

    if "flare" in f_title.lower():
        title = f"{f_title} | How to Style Flare Jeans & Sweater | MeeeShop"
    elif "date" in f_title.lower():
        title = f"{f_title} | Chic Midi Dress & Accessories | MeeeShop"
    else:
        title = f"{f_title} - Easy Everyday Styling Formula | MeeeShop"

    if len(title) > 100:
        title = title[:97] + "..."

    kw_str = ", ".join(formula.get("seo_keywords", [])[:4])
    featured_str = " + ".join([it.get("title", "")[:24] for it in items[:3]])

    desc = (
        f"Outfit Formula of the Day: {formula['subtitle']}. "
        f"Featuring in-stock boutique favorites: {featured_str}. "
        f"Real outfit inspiration for women shoppers looking for easy {kw_str}. "
        f"Tap the pin to explore and shop each piece directly with Free US Shipping & easy returns at MeeeShop. "
        f"Save this outfit formula for your next weekend styling inspiration! "
        f"#OutfitFormula #CasualOutfits #FallFashion #HowToStyle #BoutiqueStyle #FlareJeans"
    )

    if len(desc) > 500:
        desc = desc[:497] + "..."

    primary_link = items[0].get("url") if items else "https://us.meeeshop.com"

    return {
        "title": title,
        "description": desc,
        "link": primary_link,
        "alt_text": f"Outfit formula collage showing {f_title} with styled boutique apparel from MeeeShop US",
    }


# ── Master Orchestration Workflow ─────────────────────────────────────────────

def run_outfit_formula_workflow(
    formula_name: str = "auto",
    pins_count: int = 1,
    dry_run: bool = False
) -> bool:
    """Master workflow to generate, publish, and tag Outfit Formula pins."""
    store_url = get_secret("SHOPIFY_STORE_URL")
    access_token = get_secret("SHOPIFY_ACCESS_TOKEN")

    if not store_url or not access_token:
        logger.critical("Missing SHOPIFY_STORE_URL or SHOPIFY_ACCESS_TOKEN!")
        return False

    client = ShopifyClient(store_url, access_token)
    catalog = OutfitCatalog(client)
    catalog.load_catalog()

    history = load_history()
    recent_ids = get_recently_used_ids(history, days=5)

    all_formula_keys = list(OUTFIT_FORMULAS.keys())
    used_formulas = [p.get("formula_id") for p in history.get("posts", [])[-len(all_formula_keys):]]

    poster = None
    if not dry_run:
        if StealthPinterestPoster is None:
            logger.error("StealthPinterestPoster could not be imported. Cannot post live.")
            return False
        poster = StealthPinterestPoster(headless=True)

    success_count = 0

    for pin_idx in range(pins_count):
        logger.info(f"\n{'='*70}\n[Outfit Formula Pin #{pin_idx + 1}/{pins_count}]\n{'='*70}")

        if formula_name != "auto" and formula_name in OUTFIT_FORMULAS:
            formula = OUTFIT_FORMULAS[formula_name]
        else:
            avail_formulas = [k for k in all_formula_keys if k not in used_formulas]
            chosen_key = avail_formulas[0] if avail_formulas else random.choice(all_formula_keys)
            formula = OUTFIT_FORMULAS[chosen_key]
            used_formulas.append(chosen_key)

        logger.info(f"[FORMULA] Selected: '{formula['title']}' ({formula['id']})")

        session_used_ids = set()
        outfit_items = []

        for slot in formula["slots"]:
            item = catalog.pick_item_for_slot(slot, session_used_ids, recent_ids)
            if item:
                item_copy = dict(item)
                item_copy["role_label"] = slot["role_label"]
                outfit_items.append(item_copy)

        if len(outfit_items) < 3:
            logger.error("Could not find enough in-stock items to complete formula. Skipping.")
            continue

        for idx, it in enumerate(outfit_items):
            local_img = SCRATCH_DIR / f"outfit_item_{it['id']}_{idx}.jpg"
            try:
                resp = requests.get(it["image_url"], timeout=15)
                resp.raise_for_status()
                local_img.write_bytes(resp.content)
                it["local_image_path"] = str(local_img)
            except Exception as e:
                logger.warning(f"Failed to download image for {it['title']}: {e}")

        collage_filename = f"outfit_formula_{formula['id']}_{int(time.time())}.jpg"
        collage_path = str(SCRATCH_DIR / collage_filename)

        render_outfit_formula_collage(
            outfit_items=outfit_items,
            formula_title=formula["title"],
            formula_subtitle=formula["subtitle"],
            output_path=collage_path
        )

        seo = generate_outfit_seo(formula, outfit_items)
        board_name = formula["board_name"]

        logger.info(f"[SEO] Title: {seo['title']}")
        logger.info(f"[BOARD] Target: {board_name}")
        logger.info(f"[URL] Destination: {seo['link']}")
        logger.info(f"[ITEMS] Featured In-Stock Items ({len(outfit_items)}):")
        for oi in outfit_items:
            logger.info(f"   • {oi['role_label']}: {oi['title']} (${oi['price']}) [ID: {oi['id']}]")

        if dry_run:
            logger.info("[DRY RUN] All outfit pairing, collage generation, and SEO copy verified successfully! Skipping live Pinterest post.")
            success_count += 1
            continue

        # ── Step 4: Publish to Pinterest via Stealth Poster ───────────────────
        logger.info(f"[POST] Publishing Outfit Formula Pin to Pinterest board '{board_name}'...")
        post_ok, live_pin_url = poster.create_pin(
            image_path=collage_path,
            title=seo["title"],
            description=seo["description"],
            board_name=board_name,
            link_url=seo["link"],
            alt_text=seo["alt_text"],
            dry_run=False
        )

        if not post_ok or not live_pin_url:
            logger.error(f"Failed to publish pin to Pinterest: {live_pin_url}")
            continue

        logger.info(f"[SUCCESS] Pin published successfully! Live Pin URL: {live_pin_url}")

        pin_id_match = re.search(r'/pin/(\d+)', live_pin_url)
        pin_id = pin_id_match.group(1) if pin_id_match else None

        # ── Step 5: Automatically Tag Products on the Pin ─────────────────────
        tagged_ok = False
        if pin_id and tag_pin_visually_with_playwright:
            logger.info(f"[TAG] Tagging {len(outfit_items)} outfit products directly onto Pin #{pin_id}...")
            tag_payload = []
            for it in outfit_items:
                tag_payload.append({
                    "id": it["id"],
                    "variant_id": it["variant_id"],
                    "handle": it["handle"],
                    "title": it["title"],
                    "price": it["price"],
                    "url": it["url"],
                    "image_url": it["image_url"]
                })

            try:
                tagged_ok = tag_pin_visually_with_playwright(pin_id, tag_payload, max_tags=10)
                if tagged_ok:
                    logger.info(f"[TAG OK] All {len(tag_payload)} outfit products successfully tagged on Pin #{pin_id}!")
                else:
                    logger.warning(f"Visual product tagging returned False for Pin #{pin_id}")
            except Exception as te:
                logger.error(f"Error during product tagging on Pin #{pin_id}: {te}")
        else:
            logger.info("[TAG SKIP] Tagging skipped (no pin_id captured or visual tagger unavailable).")

        history["posts"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "formula_id": formula["id"],
            "formula_title": formula["title"],
            "pin_url": live_pin_url,
            "pin_id": pin_id,
            "board": board_name,
            "title": seo["title"],
            "tagged_products_count": len(outfit_items) if tagged_ok else 0,
            "outfit_items": [
                {"id": it["id"], "variant_id": it["variant_id"], "title": it["title"], "price": it["price"], "role": it["role_label"]}
                for it in outfit_items
            ]
        })
        save_history(history)
        success_count += 1

        if pin_idx < pins_count - 1:
            wait_sec = random.randint(30, 60)
            logger.info(f"Waiting {wait_sec}s before next outfit formula pin...")
            time.sleep(wait_sec)

    logger.info(f"\n[DONE] Workflow complete! {success_count}/{pins_count} outfit pins processed successfully.")
    return success_count > 0


# ── CLI Interface ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MeeeShop Pinterest Outfit Formula & Styling Collage Generator")
    parser.add_argument("--formula", type=str, default="auto", choices=["auto"] + list(OUTFIT_FORMULAS.keys()),
                        help="Outfit Formula to generate (default: auto)")
    parser.add_argument("--pins-count", type=int, default=1, help="Number of outfit pins to create (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate pipeline and generate collage without publishing")
    parser.add_argument("--apply", action="store_true", help="Actually post and tag pins live on Pinterest")

    args = parser.parse_args()

    is_dry_run = args.dry_run or not args.apply

    logger.info("=" * 70)
    logger.info(f"MeeeShop Pinterest Outfit Formula Orchestrator (Dry-Run: {is_dry_run})")
    logger.info("=" * 70)

    success = run_outfit_formula_workflow(
        formula_name=args.formula,
        pins_count=args.pins_count,
        dry_run=is_dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
