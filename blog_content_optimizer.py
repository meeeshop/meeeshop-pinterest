"""
blog_content_optimizer.py — AI Content & Board Selection Optimizer for Shopify Blog Pins
Generates 100-char search titles, 400+ char SEO descriptions, and multi-board routing for blog pins.
"""

import logging
from typing import Dict, Any, List
from ai_client import generate
from keyword_engine import get_seo_content

logger = logging.getLogger(__name__)


def generate_blog_pin_title(article: Dict[str, Any]) -> str:
    """Generate 80-100 character SEO title for blog pins"""
    title = article.get("title", "")
    blog_title = article.get("blog_title", "Fashion Blog")
    seo_data = get_seo_content("blog", [])

    prompt = f"""Create a highly searchable Pinterest pin title (80-100 chars) for this fashion blog article.

Article Title: {title}
Category: {blog_title}
Season/Event: {seo_data['event_name']}

Requirements:
- Target USA women reading fashion & outfit tips
- Use search terms naturally (e.g. "How to Style...", "10 Outfit Ideas for...", "Trendy US Boutique Style Guide")
- Max length: 100 characters (aim for 80-100 characters)
- NO hashtags, NO emojis

Reply ONLY with the title."""

    res = generate(prompt, max_tokens=40, temperature=0.6)
    if res:
        cleaned = res.strip().strip('"').strip("'")
        return cleaned[:100]

    return f"{title} | US Boutique Fashion Guide"[:100]


def generate_blog_pin_description(article: Dict[str, Any]) -> str:
    """Generate 350-450 character SEO description for blog pins"""
    title = article.get("title", "")
    excerpt = article.get("excerpt", "")
    seo_data = get_seo_content("blog", [])

    prompt = f"""Write an SEO-rich Pinterest description (350-450 chars) for this fashion blog post.

Article: {title}
Summary/Excerpt: {excerpt[:150]}
Season: {seo_data['event_name']}

Requirements:
- 3-4 natural, engaging sentences explaining what the reader will learn/discover.
- Target USA women looking for style advice, outfit inspiration, and boutique trends.
- Include a CTA: "Read the full fashion guide on the MeeeShop Blog now!"
- Length MUST be between 350 and 450 characters.
- NO hashtags inside description text.

Reply ONLY with the description text."""

    res = generate(prompt, max_tokens=140, temperature=0.7)
    if res:
        desc = res.strip().strip('"')
        if len(desc) >= 150:
            return desc[:500]

    return (
        f"Looking for new outfit inspiration? Read our latest guide on {title}. "
        f"Discover top styling tips, trend forecasts for {seo_data['event_name'].lower()}, and how to build "
        f"versatile looks from your wardrobe. Explore chic fashion ideas from MeeeShop US Boutique. "
        f"Read the full fashion guide on the MeeeShop Blog now!"
    )[:500]


def select_blog_boards(article: Dict[str, Any], available_boards: List[Dict]) -> List[Dict]:
    """Select 2-3 relevant boards for routing blog pins"""
    title_lower = (article.get("title") or "").lower()
    
    preferred_names = ["Outfit Ideas", "Style Ideas", "Everyday Style", "Trends", "Ootd #ootd", "Fashion Models"]
    
    selected = []
    board_map = {b.get("name", "").lower(): b for b in available_boards}
    
    for name in preferred_names:
        b = board_map.get(name.lower())
        if b and b not in selected:
            selected.append(b)
            if len(selected) >= 3:
                break
                
    if not selected and available_boards:
        selected = available_boards[:2]
        
    return selected
