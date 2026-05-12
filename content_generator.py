"""
content_generator.py — AI-powered Pinterest content (titles, descriptions, hashtags)
Uses ai_client_op for free AI models with fallback templates
Follows Pinterest guidelines & SEO best practices for women shoppers
"""

import logging
from typing import Dict, Any, Optional, List
from ai_client import generate

logger = logging.getLogger(__name__)


def generate_pinterest_title(product_data: Dict[str, Any]) -> str:
    """Generate Pinterest-optimized title (max 100 chars, engaging)"""

    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")

    if len(title) <= 100:
        return title

    prompt = f"""Generate a catchy Pinterest pin title (max 100 chars) for this women's fashion product:
Title: {title}
Type: {product_type}

Requirements:
- Include 1-2 power keywords (style, occasion, material)
- Be engaging & benefit-focused (e.g., "Comfy", "Flattering", "Versatile")
- End with emoji or power word that drives clicks
- NO hashtags in title
- Include size/fit info if applicable

Reply ONLY with the title, no explanation."""

    result = generate(prompt, max_tokens=50, temperature=0.7)

    if result:
        return result[:100].strip()

    # Fallback template
    power_words = ["Chic", "Stunning", "Comfy", "Versatile", "Elegant"]
    for word in power_words:
        if word.lower() not in title.lower():
            return f"{word} {title[:80]}"

    return title[:100]


def generate_pinterest_description(product_data: Dict[str, Any], board_name: str) -> str:
    """Generate Pinterest description (max 300 chars for desc field)"""

    title = product_data.get("title", "")
    product_type = product_data.get("product_type", "")
    description = product_data.get("description", "")
    tags = ", ".join(product_data.get("tags", [])[:3])

    prompt = f"""Create a Pinterest pin description for women shoppers (max 250 chars):
Product: {title}
Type: {product_type}
Board: {board_name}
Tags: {tags}

Requirements:
- Include lifestyle benefit (comfort, style, quality)
- Add 2-3 relevant keywords naturally
- Include a call-to-action phrase
- Mention if made in USA
- Keep it natural & conversational
- NO hashtags

Reply ONLY with description."""

    result = generate(prompt, max_tokens=100, temperature=0.7)

    if result:
        desc = result.strip()
        return desc[:300]

    # Fallback template
    return f"Discover this {product_type.lower() or 'item'}. Perfect for {board_name.lower()}. Shop now!"[:300]


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
- Trend hashtags (#SpringStyle, #Summer2026)
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
- What women search for (style keywords: "casual", "dressy", "boho")
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
    """Generate complete Pinterest content package"""

    logger.info(f"Generating content for: {product_data.get('title', 'Unknown')}")

    return {
        "pin_title": generate_pinterest_title(product_data),
        "pin_description": generate_pinterest_description(product_data, board_name),
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
