"""
blog_content_optimizer.py — AI Content & Board Selection Optimizer for Shopify Blog Pins
Generates 100-char search titles, 400+ char SEO descriptions, and multi-board routing for blog pins.
"""

import logging
from typing import Dict, Any, List
from ai_client import generate
from keyword_engine import get_seo_content

logger = logging.getLogger(__name__)


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
    "article:",
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


def generate_blog_pin_title(article: Dict[str, Any]) -> str:
    """Generate 80-100 character SEO title for blog pins containing actual article title"""
    title = (article.get("title") or "").strip()
    blog_title = (article.get("blog_title") or "Fashion Blog").strip()
    seo_data = get_seo_content("blog", [])

    if not title:
        return "Women's Boutique Style & Fashion Guide | MeeeShop"

    clean_fallback = f"{title} | US Boutique Fashion Guide"[:100]

    prompt = f"""Write an engaging Pinterest pin title (under 80 chars) for this fashion article:
Article Title: {title}
Category: {blog_title}

Rules:
- MUST include key words from article title: "{title}"
- Max 80 characters
- NO prompt words, NO hashtags, NO emojis

Reply ONLY with the title string."""

    res = generate(prompt, max_tokens=40, temperature=0.5)
    if res:
        cleaned = res.strip().strip('"').strip("'").splitlines()[0].strip()
        if not _is_prompt_leak(cleaned) and len(cleaned) >= 5:
            if "MeeeShop" not in cleaned and len(cleaned) <= 75:
                cleaned = f"{cleaned} — MeeeShop"
            return cleaned[:100]

    return clean_fallback


def generate_blog_pin_description(article: Dict[str, Any]) -> str:
    """Generate 350-450 character SEO description for blog pins"""
    title = (article.get("title") or "").strip()
    excerpt = (article.get("excerpt") or "").strip()
    seo_data = get_seo_content("blog", [])

    clean_fallback = (
        f"Looking for fresh style inspiration? Explore our latest style feature on {title}. "
        f"Discover effortless outfit ideas, styling tips for {seo_data['event_name'].lower()}, and modern wardrobe essentials. "
        f"MeeeShop brings you curated boutique trends and fashion advice. "
        f"Read the full fashion guide on the MeeeShop Blog now!"
    )[:500]

    prompt = f"""Write an SEO-rich Pinterest description (350-450 chars) for:
Article: {title}
Summary: {excerpt[:150]}

Requirements:
- 3-4 natural, engaging sentences explaining what the reader will discover in {title}.
- Target USA women looking for outfit inspiration and boutique trends.
- Include a CTA: "Read the full fashion guide on the MeeeShop Blog now!"
- Length MUST be between 350 and 450 characters.
- NO hashtags inside description text.

Reply ONLY with the description text."""

    res = generate(prompt, max_tokens=140, temperature=0.6)
    if res:
        desc = res.strip().strip('"').strip("'")
        if not _is_prompt_leak(desc) and len(desc) >= 150:
            return desc[:500]

    return clean_fallback


def select_blog_boards(
    article: Dict[str, Any], available_boards: List[Dict]
) -> List[Dict]:
    """
    Select relevant boards for routing blog pins, prioritizing dedicated blog boards
    and matching topic boards across all available account boards.

    Args:
        article: Shopify blog article dict
        available_boards: List of board dicts fetched from Pinterest API

    Returns:
        List of board dicts (prioritized target boards)
    """
    from board_mapping import BLOG_BOARDS

    title_lower = (article.get("title") or "").lower()
    excerpt_lower = (article.get("excerpt") or "").lower()
    full_text = f"{title_lower} {excerpt_lower}"

    board_map = {b.get("name", "").lower(): b for b in available_boards}

    selected = []

    # 1. Dedicated Blog Boards
    for name in BLOG_BOARDS:
        b = board_map.get(name.lower())
        if b and b not in selected:
            selected.append(b)

    # 2. Topic Keyword Matching across all available boards
    keywords = [
        "dress",
        "top",
        "blouse",
        "jeans",
        "jacket",
        "sweater",
        "fall",
        "winter",
        "summer",
        "spring",
        "chic",
        "casual",
        "ootd",
    ]
    for b_dict in available_boards:
        b_name = b_dict.get("name", "").lower()
        if any(kw in full_text and kw in b_name for kw in keywords):
            if b_dict not in selected:
                selected.append(b_dict)

    if not selected and available_boards:
        selected = available_boards[:3]

    return selected

