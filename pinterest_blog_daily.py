"""
pinterest_blog_daily.py — Post Shopify blog articles as editorial pins to Pinterest.
Updated with SEO title/description optimization & multi-board distribution.
"""

import json
import logging
import os
import sys
import random
import time
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient
from image_overlay import create_pin_image
from blog_content_optimizer import generate_blog_pin_title, generate_blog_pin_description, select_blog_boards
from keyword_engine import get_seo_content

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "blog_posting_history.json"
MAX_BLOGS_PER_RUN = 2  # Updated to 2 blog pins per daily run
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")

def load_history() -> Dict[str, Any]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"posts": []}

def save_history(history: Dict[str, Any]) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, default=str), encoding="utf-8"
    )

def is_recent(timestamp_str: str, days: int) -> bool:
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        return datetime.now() - ts < timedelta(days=days)
    except Exception:
        return False

def was_recently_posted(article_id: str, history: Dict[str, Any]) -> bool:
    # Cooldown for same blog post (14 days)
    for post in history.get("posts", []):
        if str(post.get("product_id")) == str(article_id):
            if is_recent(post.get("timestamp"), 14):
                return True
                
    # Also check other history files (4 days cooldown for cross-script safety)
    other_histories = [
        ("posting_history_v2.json", "posts", "timestamp"),
        ("refresh_history_v2.json", "refreshes", "timestamp"),
        ("video_posting_history.json", "posts", "posted_at")
    ]
    for filename, list_key, time_key in other_histories:
        path = Path(__file__).parent / filename
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data.get(list_key, []):
                    item_id = item.get("product_id") or item.get("id")
                    if str(item_id) == str(article_id):
                        ts_str = item.get(time_key)
                        if ts_str and is_recent(ts_str, 4):
                            return True
            except Exception:
                pass
    return False

def fetch_shopify_articles(shopify: ShopifyClient, limit: int = 15) -> List[Dict[str, Any]]:
    query = """
    query ($first: Int!) {
      articles(first: $first) {
        edges {
          node {
            id
            title
            handle
            summary
            body
            image {
              url
            }
            blog {
              title
              handle
            }
            publishedAt
          }
        }
      }
    }
    """
    try:
        res = shopify.run_graphql(query, {"first": limit})
        edges = res.get("data", {}).get("articles", {}).get("edges", [])
        articles = []
        for edge in edges:
            node = edge["node"]
            raw_id = node.get("id", "")
            art_id = raw_id.split("/")[-1] if "/" in raw_id else raw_id
            
            img_url = node.get("image", {}).get("url", "") if node.get("image") else ""
            articles.append({
                "id": art_id,
                "title": node.get("title"),
                "handle": node.get("handle"),
                "excerpt": node.get("summary") or "",
                "image_url": img_url,
                "blog_title": node.get("blog", {}).get("title", "MeeeShop Blog"),
                "blog_handle": node.get("blog", {}).get("handle", "news"),
                "published_at": node.get("publishedAt"),
            })
        return articles
    except Exception as e:
        logger.error(f"Failed to fetch Shopify blog articles: {e}")
        return []

def download_image(url: str, save_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        logger.error(f"Image download failed: {e}")
        return False

def run_blog_posting() -> None:
    shopify_url    = get_secret("SHOPIFY_STORE_URL")
    shopify_token  = get_secret("SHOPIFY_ACCESS_TOKEN")
    store_base_url = get_secret("STORE_BASE_URL")

    if not shopify_url or not shopify_token:
        raise ValueError("SHOPIFY_STORE_URL / SHOPIFY_ACCESS_TOKEN not set")

    if DRY_RUN:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE — no pins will be posted to Pinterest")
        logger.info("=" * 60)

    # 1. Shopify Client & Fetch articles
    shopify = ShopifyClient(shopify_url, shopify_token)
    articles = fetch_shopify_articles(shopify, limit=20)
    if not articles:
        logger.warning("No blog articles found on Shopify. Gracefully exiting.")
        return

    logger.info(f"Loaded {len(articles)} blog articles from Shopify")

    # 2. Filter eligible articles
    history = load_history()
    eligible = [art for art in articles if not was_recently_posted(art["id"], history)]
    if not eligible:
        logger.info("All articles have been posted recently or within the cooldown period. Skipping execution to avoid spam.")
        return

    # Shuffle to vary postings
    random.shuffle(eligible)
    to_post = eligible[:MAX_BLOGS_PER_RUN]
    
    logger.info(f"Selected {len(to_post)} article(s) to post")

    # 3. Pinterest Client Login
    pinterest = PinterestClient()
    boards = []
    if not DRY_RUN:
        if not pinterest.login():
            raise RuntimeError("Pinterest login failed")
        logger.info("✓ Pinterest login succeeded")
        boards = pinterest.fetch_boards()

    temp_dir = Path(tempfile.gettempdir())

    for article in to_post:
        logger.info(f"\n--- Posting Article: '{article['title']}' ---")
        
        # Optimize title and description with AI Keyword Engine
        pin_title = generate_blog_pin_title(article)
        pin_desc = generate_blog_pin_description(article)
        seo_info = get_seo_content("blog", [])
        hashtags = " ".join(seo_info["demographic_tags"][:3] + seo_info["seasonal_hashtags"][:2])
        full_desc = f"{pin_desc}\n\n{hashtags}"
        
        blog_url = f"{store_base_url.rstrip('/')}/blogs/{article['blog_handle']}/{article['handle']}"
        alt_text = f"MeeeShop Fashion Blog Article: {article['title']}"

        # Clean HTML tags from excerpt if present
        clean_excerpt = article['excerpt'].replace("<p>", "").replace("</p>", "").strip()[:140]
        if not clean_excerpt:
            clean_excerpt = "Read our latest article for styling tips, outfits, and fashion trends..."

        # Temporary files for processing
        temp_src = temp_dir / f"blog_src_{article['id']}.jpg"
        temp_final = temp_dir / f"blog_final_{article['id']}.jpg"

        # Download original blog image
        fallback_img = Path(__file__).parent / "default_blog_img.jpg"
        if article["image_url"]:
            if not download_image(article["image_url"], temp_src):
                logger.error(f"Failed to download blog image. Skipping article.")
                continue
        else:
            if not fallback_img.exists():
                from PIL import Image
                Image.new("RGB", (800, 600), (220, 210, 205)).save(fallback_img)
            temp_src = fallback_img

        # Create Blog Pin Image using template (Direct White/Cream Text Overlay)
        final_image = create_pin_image(
            product_image_path=str(temp_src),
            title=pin_title,
            category=article["blog_title"],
            price=None,
            cta="READ ARTICLE ★ US.MEEESHOP.COM",
            output_path=str(temp_final),
            template_index=16
        )

        if not final_image:
            logger.error(f"Failed to generate template image for article: {article['title']}")
            continue

        # Target boards selection (Multi-board targeting)
        target_boards = select_blog_boards(article, boards if boards else [{"name": "Style Ideas", "id": "fallback"}])
        target_board = target_boards[0] if target_boards else {"name": "Style Ideas", "id": None}
        board_name = target_board.get("name", "Style Ideas")
        board_id = target_board.get("id")
        
        logger.info(f"Target Board: {board_name} (id={board_id})")

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would post blog pin: '{pin_title}' to board '{board_name}'")
            if temp_src != fallback_img:
                temp_src.unlink(missing_ok=True)
            temp_final.unlink(missing_ok=True)
            continue

        if not board_id and not DRY_RUN:
            logger.error(f"No board ID found for posting. Skipping article.")
            if temp_src != fallback_img:
                temp_src.unlink(missing_ok=True)
            temp_final.unlink(missing_ok=True)
            continue

        # Pin creation
        success, pin_id = pinterest.create_pin(
            image_path=final_image,
            title=pin_title,
            description=full_desc,
            board_id=board_id,
            url=blog_url,
            alt_text=alt_text
        )

        # Cleanup
        if temp_src.exists() and temp_src != fallback_img:
            temp_src.unlink(missing_ok=True)
        temp_final.unlink(missing_ok=True)

        if success:
            logger.info(f"✓ Posted article successfully! Pin ID: {pin_id}")
            history["posts"].append({
                "product_id": str(article["id"]),
                "product_title": article["title"],
                "pin_title": pin_title,
                "pin_id": pin_id,
                "board": board_name,
                "url": blog_url,
                "timestamp": datetime.now().isoformat()
            })
            save_history(history)
        else:
            logger.error(f"✗ Failed to create blog article pin: {pin_id}")


if __name__ == "__main__":
    run_blog_posting()

