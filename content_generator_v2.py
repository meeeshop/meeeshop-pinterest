"""
content_generator_v2.py — Phase 2 Pinterest content (USA-targeted, SEO-first)

Changes from V1:
  - Titles: search-term-first format "[Keyword] | [Benefit] | MeeeShop" (100 char max)
  - Descriptions: expanded 150-200 chars with natural sentences + USA context
  - Hashtags: added USA-specific base tags + seasonal/occasion hooks
  - Alt text: unchanged (already correct)
  - Seasonal hooks: injected from current month automatically
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from ai_client import generate

logger = logging.getLogger(__name__)


# ── Seasonal context ──────────────────────────────────────────────────────────

def _get_seasonal_context() -> Dict[str, str]:
    month = datetime.now().month
    seasons = {
        (3, 4, 5):  {"season": "Spring", "occasion": "Spring Outfits"},
        (6, 7, 8):  {"season": "Summer", "occasion": "Summer Style"},
        (9, 10, 11): {"season": "Fall",  "occasion": "Fall Fashion"},
        (12, 1, 2): {"season": "Winter", "occasion": "Winter Looks"},
    }
    upcoming = {
        1: "Valentine's Day",  2: "Valentine's Day",
        3: "Spring Break",     4: "Easter",
        5: "Mother's Day",     6: "Summer Vacation",
        7: "4th of July",      8: "Back to School",
        9: "Fall Fashion",     10: "Halloween",
        11: "Thanksgiving",    12: "Holiday Season",
    }
    ctx = {"season": "Summer", "occasion": "Summer Style"}
    for months, val in seasons.items():
        if month in months:
            ctx = val
            break
    ctx["upcoming"] = upcoming.get(month, ctx["season"])
    return ctx


# ── Title ─────────────────────────────────────────────────────────────────────

def generate_pinterest_title(product_data: Dict[str, Any]) -> str:
    """Search-first title: '[Keyword] | [Benefit] | MeeeShop' (max 100 chars)"""
    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    ctx = _get_seasonal_context()

    prompt = f"""Create a Pinterest pin title for this women's fashion product.

Product: {title}
Type: {product_type}
Season: {ctx['season']}

Format EXACTLY: [Search Keyword] | [Benefit] | MeeeShop
Rules:
- First part: what women search for (e.g. "Women's Midi Dress", "Floral Summer Top")
- Second part: 1 benefit word or USA-focus (Flattering, Chic, US Boutique, Trendy)
- Always end with "| MeeeShop"
- Total under 100 chars, NO hashtags, NO emojis

Example: Women's Wrap Dress | US Boutique | MeeeShop

Reply ONLY with the title, nothing else."""

    result = generate(prompt, max_tokens=40, temperature=0.6)
    if result:
        cleaned = result.strip().strip('"').strip("'")
        if "MeeeShop" not in cleaned:
            cleaned = f"{cleaned} | MeeeShop"
        return cleaned[:100]

    # Fallback: build from product title
    base = f"Women's {product_type}" if product_type else title[:30]
    return f"{base} | US Boutique | MeeeShop"[:100]


# ── Description ───────────────────────────────────────────────────────────────

def generate_pinterest_description(product_data: Dict[str, Any], board_name: str) -> str:
    """Expanded description 150-200 chars with USA context and natural CTA"""
    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    tags = ", ".join(product_data.get("tags", [])[:3])
    ctx = _get_seasonal_context()

    prompt = f"""Write a Pinterest pin description for a USA women's fashion store.

Product: {title}
Type: {product_type}
Tags: {tags}
Board: {board_name}
Season: {ctx['season']} — upcoming: {ctx['upcoming']}

Requirements:
- 2-3 natural sentences, 150-200 characters total
- Mention style benefit or occasion
- MUST include: "Free shipping within the USA" or "Free US shipping"
- End with a CTA: "Shop now at MeeeShop" or "Tap to shop"
- NO hashtags in description
- Sound genuine, not spammy

Reply ONLY with the description, nothing else."""

    result = generate(prompt, max_tokens=80, temperature=0.7)
    if result:
        desc = result.strip().strip('"')
        return desc[:500]  # Pinterest allows up to 500 chars

    return f"Elevate your {ctx['season'].lower()} wardrobe with this {product_type.lower() or 'trendy US boutique style'}. Free shipping within the USA! Shop now at MeeeShop."[:500]


# ── Alt text ──────────────────────────────────────────────────────────────────

def generate_alt_text(product_data: Dict[str, Any]) -> str:
    """Accessibility alt text (max 125 chars) — unchanged from V1"""
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
        return f"{color} {product_type or 'item'} from MeeeShop"[:125]
    return f"{product_type or 'Fashion item'} from MeeeShop"[:125]


# ── Hashtags ──────────────────────────────────────────────────────────────────

def generate_hashtags(product_data: Dict[str, Any], board_name: str) -> List[str]:
    """10-15 hashtags: USA-specific base + product-specific AI tags + seasonal"""
    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    tags = product_data.get("tags", [])
    ctx = _get_seasonal_context()

    # V2 base: added USA signals + seasonal + free shipping
    base_hashtags = [
        "#USAWomensFashion",
        "#USABoutique",
        "#FreeShippingUSA",
        "#ShopSmallUSA",
        "#USAShopping",
        f"#{ctx['season']}Style",
        "#AmericanStyle",
    ]

    prompt = f"""Generate 6-8 Pinterest hashtags for women's fashion (use #):
Product: {title}
Type: {product_type}
Tags: {", ".join(tags[:3])}
Board: {board_name}
Season: {ctx['season']}, Occasion: {ctx['upcoming']}

Focus on: USA women's fashion tags, US boutique style, occasion tags
Reply ONLY with hashtags separated by spaces."""

    result = generate(prompt, max_tokens=80, temperature=0.6)
    if result:
        ai_tags = [h.strip() for h in result.split() if h.startswith("#")]
        return base_hashtags + ai_tags[:8]

    return base_hashtags + [f"#{tag.replace(' ', '')}" for tag in tags[:3]]


# ── Keywords ──────────────────────────────────────────────────────────────────

def generate_keywords_for_seo(product_data: Dict[str, Any]) -> List[str]:
    """SEO keywords — unchanged logic from V1"""
    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")

    prompt = f"""Generate 8-12 search keywords for this women's fashion product:
Title: {title}
Type: {product_type}

Focus on: USA women's boutique, style keywords, occasion keywords, long-tail phrases
Reply ONLY with keywords separated by commas."""

    result = generate(prompt, max_tokens=100, temperature=0.5)
    if result:
        return [k.strip() for k in result.split(",")]

    return [
        product_type.lower() if product_type else "usa women's boutique",
        "usa women's fashion",
        "shop us boutique online",
        "free shipping usa",
    ]


# ── Package ───────────────────────────────────────────────────────────────────

def generate_content_package(product_data: Dict[str, Any], board_name: str) -> Dict[str, Any]:
    """Complete Pinterest content package — V2"""
    logger.info(f"[V2] Generating content for: {product_data.get('title', 'Unknown')}")
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
        "title": "Vintage High-Waisted Mom Jeans in Dark Wash",
        "product_type": "Jeans",
        "description": "Classic 90s-inspired high-waisted jeans",
        "tags": ["vintage", "jeans", "denim"],
    }
    content = generate_content_package(test_product, "Everyday Style")
    print(f"Title:       {content['pin_title']}")
    print(f"Description: {content['pin_description']}")
    print(f"Hashtags:    {' '.join(content['hashtags'])}")
    print(f"Keywords:    {', '.join(content['keywords'])}")


if __name__ == "__main__":
    main()
