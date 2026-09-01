"""
content_generator.py — AI-powered Pinterest content (titles, descriptions, hashtags)
Uses ai_client_op for free AI models with fallback templates
Follows Pinterest guidelines & SEO best practices for women shoppers
"""

import logging
import sys
from typing import Dict, Any, Optional, List
from pathlib import Path
from ai_client import generate

logger = logging.getLogger(__name__)

# Secrets are loaded by the entry-point (pinterest_client.py / pinterest_daily.py)
# via inject_to_env() before this module is imported. No action needed here.


PROMPT_LEAK_KEYWORDS = [
    "we need",
    "create a",
    "here is",
    "here's",
    "natural, highly searchable",
    "highly searchable",
    "pinterest pin title",
    "for usa women shoppers",
    "rules:",
    "requirements:",
    "product:",
    "type:",
    "season/event:",
    "occasion focus:",
    "target event",
    "reply only",
    "prompt:",
    "task:",
    "ai:",
    "shopper",
    "sure!",
    "sure,",
    "write an seo",
]


def _is_prompt_leak(text: str) -> bool:
    if not text or not isinstance(text, str):
        return True
    t_lower = text.lower().strip()
    return any(kw in t_lower for kw in PROMPT_LEAK_KEYWORDS)


def generate_pinterest_title(product_data: Dict[str, Any]) -> str:
    """Generate Pinterest-optimized title containing actual product title"""
    title = (product_data.get("title") or "").strip()
    product_type = (product_data.get("product_type") or "").strip()

    if not title:
        return "Women's Boutique Fashion | MeeeShop"

    clean_fallback = f"{title} | MeeeShop"[:80]

    prompt = f"""Write a concise Pinterest pin title (under 50 chars) for:
Product: {title}
Type: {product_type}

Rules:
- MUST include the product name: "{title}"
- Max 50 characters
- NO hashtags, NO emojis, NO explanations

Reply ONLY with the title string."""

    result = generate(prompt, max_tokens=30, temperature=0.5)

    if result:
        cleaned = result.strip().strip('"').strip("'").splitlines()[0].strip()
        if not _is_prompt_leak(cleaned) and len(cleaned) >= 5:
            return cleaned[:80]

    return clean_fallback


def generate_pinterest_description(product_data: Dict[str, Any], board_name: str) -> str:
    """Generate Pinterest description (max 100 chars)"""

    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    tags = ", ".join(product_data.get("tags", [])[:2])

    prompt = f"""Create a Pinterest pin description (max 100 chars):
Product: {title}
Type: {product_type}
Tags: {tags}

Requirements:
- Brief & engaging
- Include 1-2 keywords naturally, aligning with 2026 Pinterest trends (e.g. Poetcore, Off-Duty Athlete, Vamp Romantic)
- Mention quality/style benefit
- Call-to-action: "Shop Now" or "Discover"
- NO hashtags

Reply ONLY with description (under 100 chars), no explanation."""

    result = generate(prompt, max_tokens=50, temperature=0.7)

    if result:
        desc = result.strip()
        return desc[:100]

    # Fallback template
    return f"Discover this {product_type.lower() or 'item'} today!"[:100]


def generate_alt_text(product_data: Dict[str, Any]) -> str:
    """Generate accessibility alt text for pin image (max 125 chars)"""

    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    color = product_data.get("color", "")

    prompt = f"""Generate concise alt text for an image of this product (max 125 chars):
Product: {title}
Type: {product_type}
Color: {color if color else "various"}

Requirements:
- Describe what's in the image (not "image of" or "picture of")
- Include product type and main features
- Helpful for screen readers
- Be concise but descriptive
- NO marketing language
- Format: "Product type, style details, key features"

Example: "Blue denim jacket with button front and chest pockets"

Reply ONLY with alt text (under 125 chars), no explanation."""

    result = generate(prompt, max_tokens=60, temperature=0.5)

    if result:
        alt = result.strip()
        return alt[:125]

    # Fallback: Simple descriptive alt text
    if color:
        return f"{color} {product_type or 'item'} from MeeeShop"[:125]
    return f"{product_type or 'Fashion item'} from MeeeShop"[:125]


def generate_hashtags(product_data: Dict[str, Any], board_name: str) -> List[str]:
    """Generate Pinterest hashtags (10-15 relevant to USA women fashion)"""

    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    tags = product_data.get("tags", [])

    # Base hashtags (always include these)
    base_hashtags = [
        "#WomensStyle",
        "#FashionFind",
        "#ShopSmall",
        "#WomensFashion",
        "#StyleInspo",
    ]

    prompt = f"""Generate 8-10 relevant Pinterest hashtags for women shoppers (use #):
Product: {title}
Type: {product_type}
Tags: {", ".join(tags[:3])}
Board: {board_name}

Focus on:
- Style/occasion hashtags (#ClassyWomensFashion, #EverydayStyle)
- Demographic hashtags (#WomenOver30, #CurvyFashion if applicable)
- 2026 Trend hashtags (#Poetcore, #OffDutyAthlete, #VampRomantic, #GimmeGummy, #Summer2026)
- Search-friendly hashtags

Reply ONLY with hashtags separated by spaces, no explanation."""

    result = generate(prompt, max_tokens=80, temperature=0.6)

    if result:
        hashtags = [h.strip() for h in result.split() if h.startswith("#")]
        return base_hashtags + hashtags[:8]

    # Fallback
    return base_hashtags + [f"#{tag.replace(' ', '')}" for tag in tags[:3]]


def generate_keywords_for_seo(product_data: Dict[str, Any]) -> List[str]:
    """Generate keywords for SEO optimization in pin metadata"""

    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")

    prompt = f"""Generate 8-12 relevant search keywords for this women's fashion product:
Title: {title}
Type: {product_type}

Focus on:
- What women search for (style keywords: "casual", "dressy", "boho", "poetcore", "off-duty athlete", "vamp romantic")
- Occasion keywords: party, work, casual, date night
- Material/fit keywords if evident
- Long-tail phrases (2-3 word combinations)

Reply ONLY with keywords separated by commas."""

    result = generate(prompt, max_tokens=100, temperature=0.5)

    if result:
        keywords = [k.strip() for k in result.split(",")]
        return keywords

    # Fallback
    return [
        product_type.lower() if product_type else "women's clothing",
        "women's fashion",
        "shop women's style",
    ]


def generate_content_package(product_data: Dict[str, Any], board_name: str) -> Dict[str, Any]:
    """Generate complete Pinterest content package (including alt text for accessibility)"""

    logger.info(f"Generating content for: {product_data.get('title', 'Unknown')}")

    return {
        "pin_title": generate_pinterest_title(product_data),
        "pin_description": generate_pinterest_description(product_data, board_name),
        "pin_alt_text": generate_alt_text(product_data),
        "hashtags": generate_hashtags(product_data, board_name),
        "keywords": generate_keywords_for_seo(product_data),
    }


def main():
    """Test content generator"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    test_product = {
        "title": "Vintage High-Waisted Mom Jeans in Dark Wash",
        "product_type": "Jeans",
        "description": "Classic 90s-inspired high-waisted jeans with vintage detailing",
        "tags": ["vintage", "jeans", "denim"],
    }

    content = generate_content_package(test_product, "Pants & Jeans")

    print("Generated Content Package:")
    print(f"Title: {content['pin_title']}")
    print(f"Description: {content['pin_description']}")
    print(f"Hashtags: {' '.join(content['hashtags'])}")
    print(f"Keywords: {', '.join(content['keywords'])}")


if __name__ == "__main__":
    main()
