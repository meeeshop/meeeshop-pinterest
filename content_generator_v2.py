"""
content_generator_v2.py — Phase 2 Pinterest content (USA-targeted, SEO-first)

Updated for 2026 USA Women's Fashion SEO:
  - Titles: Natural sentence search titles (up to 100 chars), incorporating search terms & brand context
  - Descriptions: Keyword-rich 350-450 char descriptions with semantic phrases + USA free shipping CTA
  - Hashtags: Seasonal + occasion + demographic tags from keyword_engine
  - Alt text: Detailed accessibility & feature description
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from ai_client import generate
from keyword_engine import get_seo_content

logger = logging.getLogger(__name__)


# ── Title ─────────────────────────────────────────────────────────────────────

def generate_pinterest_title(product_data: Dict[str, Any]) -> str:
    """Natural sentence search title up to 100 chars: '[Search Term] for [Occasion/Season] — MeeeShop US Boutique'"""
    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    seo_data = get_seo_content(product_type, product_data.get("tags", []))
    
    event = seo_data["event_name"]
    occasion = seo_data["occasion_keywords"][0] if seo_data["occasion_keywords"] else "Everyday Chic"

    prompt = f"""Create a natural, highly searchable Pinterest pin title for USA women shoppers.

Product: {title}
Type: {product_type}
Season/Event: {event}
Occasion Focus: {occasion}

Rules:
- Format: Natural sentence or descriptive phrase (e.g. "Chic Floral Midi Dress for Summer Outings — MeeeShop US Boutique")
- Max length: 100 characters (use as close to 80-100 characters as possible for maximum indexing)
- Include key search terms women use on Pinterest (style, fit, occasion)
- NO hashtags, NO emojis, NO pure pipe-spam '| | |'

Reply ONLY with the title string."""

    result = generate(prompt, max_tokens=50, temperature=0.6)
    if result:
        cleaned = result.strip().strip('"').strip("'")
        if "MeeeShop" not in cleaned and len(cleaned) <= 80:
            cleaned = f"{cleaned} — MeeeShop US Boutique"
        return cleaned[:100]

    # Fallback search title
    base = f"Chic Women's {product_type or 'Fashion Outfit'}"
    fallback = f"{base} for {occasion.capitalize()} — MeeeShop US Boutique"
    return fallback[:100]


# ── Description ───────────────────────────────────────────────────────────────

def generate_pinterest_description(product_data: Dict[str, Any], board_name: str) -> str:
    """Expanded SEO description 350-450 chars with USA context, search terms & CTA"""
    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    tags = ", ".join(product_data.get("tags", [])[:3])
    seo_data = get_seo_content(product_type, product_data.get("tags", []))
    
    seasonal_kw = ", ".join(seo_data["seasonal_keywords"][:3])
    occasion_kw = ", ".join(seo_data["occasion_keywords"][:3])

    prompt = f"""Write an SEO-rich Pinterest pin description for a USA women's fashion store.

Product: {title}
Type: {product_type}
Tags: {tags}
Board: {board_name}
Target Event/Season: {seo_data['event_name']}
Target Search Terms to weave in naturally: {seasonal_kw}, {occasion_kw}

Requirements:
- Length MUST be between 350 and 450 characters (Pinterest ranks detailed descriptions much higher).
- Write 3-4 fluid, inspiring sentences highlighting fit, styling versatility, and quality.
- MUST explicitly include: "Free shipping within the USA" or "Fast & free US shipping".
- End with a compelling CTA: "Tap to shop your size at MeeeShop today!" or "Discover more boutique finds at MeeeShop."
- NO hashtags inside the description text itself.

Reply ONLY with the description text."""

    result = generate(prompt, max_tokens=150, temperature=0.7)
    if result:
        desc = result.strip().strip('"')
        if len(desc) >= 150:
            return desc[:500]

    # Detailed Fallback
    return (
        f"Elevate your wardrobe with the {title}. Perfectly styled for {seo_data['event_name'].lower()} "
        f"and {seo_data['occasion_keywords'][0]}, this versatile piece delivers effortless style and comfort. "
        f"Whether you're dressing up for date night or keeping it casual for weekend errands, MeeeShop brings you "
        f"trendy boutique fashion. Enjoy free shipping within the USA! Tap to shop your size now at MeeeShop."
    )[:500]


# ── Alt text ──────────────────────────────────────────────────────────────────

def generate_alt_text(product_data: Dict[str, Any]) -> str:
    """Accessibility alt text (max 125 chars)"""
    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    color = product_data.get("color", "")

    prompt = f"""Generate concise alt text for an image of this product (max 125 chars):
Product: {title}
Type: {product_type}
Color: {color if color else "various"}

- Describe what's in the image (not "image of" or "picture of")
- Include product type and main features
- NO marketing language
- Format: "Product type, style details, key features"

Reply ONLY with alt text (under 125 chars), no explanation."""

    result = generate(prompt, max_tokens=60, temperature=0.5)
    if result:
        return result.strip()[:125]

    if color:
        return f"{color} {product_type or 'item'} from MeeeShop US Boutique"[:125]
    return f"{product_type or 'Fashion item'} from MeeeShop US Boutique"[:125]


# ── Hashtags ──────────────────────────────────────────────────────────────────

def generate_hashtags(product_data: Dict[str, Any], board_name: str) -> List[str]:
    """10-15 hashtags combining demographic, seasonal, occasion, and AI-generated terms"""
    product_type = product_data.get("product_type", "")
    seo_data = get_seo_content(product_type, product_data.get("tags", []))

    base_hashtags = (
        seo_data["demographic_tags"][:4] +
        seo_data["seasonal_hashtags"][:3] +
        ["#OutfitInspo", "#FashionUnder50", "#ShopBoutique"]
    )

    prompt = f"""Generate 5 additional trending Pinterest hashtags for women's fashion (starting with #):
Product: {product_data.get('title', '')}
Type: {product_type}
Board: {board_name}

Focus on search tags women use for boutique shopping in the USA.
Reply ONLY with hashtags separated by spaces."""

    result = generate(prompt, max_tokens=50, temperature=0.6)
    if result:
        ai_tags = [h.strip() for h in result.split() if h.startswith("#")]
        return list(dict.fromkeys(base_hashtags + ai_tags))[:15]

    return base_hashtags[:12]


# ── Keywords ──────────────────────────────────────────────────────────────────

def generate_keywords_for_seo(product_data: Dict[str, Any]) -> List[str]:
    """SEO keywords for search metadata"""
    product_type = product_data.get("product_type", "")
    seo_data = get_seo_content(product_type, product_data.get("tags", []))

    return (
        seo_data["seasonal_keywords"][:3] +
        seo_data["occasion_keywords"][:3] +
        ["free shipping usa", "us womens boutique", "affordable womens fashion"]
    )


# ── Package ───────────────────────────────────────────────────────────────────

def generate_content_package(product_data: Dict[str, Any], board_name: str) -> Dict[str, Any]:
    """Complete Pinterest content package — V2 Overhauled"""
    logger.info(f"[V2 Overhaul] Generating content for: {product_data.get('title', 'Unknown')}")
    return {
        "pin_title":       generate_pinterest_title(product_data),
        "pin_description": generate_pinterest_description(product_data, board_name),
        "pin_alt_text":    generate_alt_text(product_data),
        "hashtags":        generate_hashtags(product_data, board_name),
        "keywords":        generate_keywords_for_seo(product_data),
    }


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    test_product = {
        "title": "Floral Print Puff Sleeve Midi Dress",
        "product_type": "Dress",
        "description": "Chic floral midi dress with puff sleeves and cinched waist",
        "tags": ["floral", "dress", "summer"],
    }
    content = generate_content_package(test_product, "Dresses")
    print("\n--- GENERATED CONTENT PACKAGE ---")
    print(f"Title ({len(content['pin_title'])} chars): {content['pin_title']}")
    print(f"Description ({len(content['pin_description'])} chars): {content['pin_description']}")
    print(f"Hashtags ({len(content['hashtags'])} tags): {' '.join(content['hashtags'])}")
    print(f"Keywords: {', '.join(content['keywords'])}")


if __name__ == "__main__":
    main()

