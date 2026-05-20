"""
shopify_products.py — Fetch Shopify products optimized for Pinterest pinning
Integrates with meeeshop-invt GraphQL API or REST API
"""

import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

# Load secrets
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from secrets_manager import inject_to_env, get_secret
inject_to_env()


class ShopifyClient:
    """Fetch products from Shopify store"""

    def __init__(self, store_url: str, access_token: str):
        self.store_url = store_url.rstrip("/")
        self.access_token = access_token
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    def get_products(
        self,
        collection: Optional[str] = None,
        limit: int = 50,
        status: str = "active",
        published: bool = True,
    ) -> List[Dict[str, Any]]:
        """Fetch products from store"""

        url = f"{self.store_url}/admin/api/2024-01/products.json"

        params = {
            "limit": min(limit, 250),
            "status": status,
            "fields": "id,title,handle,image,images,body_html,vendor,product_type,tags,published_at,variants",
        }

        if published:
            params["published_status"] = "published"

        try:
            logger.debug(f"Fetching products from: {url}")
            logger.debug(f"Params: {params}")
            resp = requests.get(url, headers=self.headers, params=params, timeout=30)
            resp.raise_for_status()
            products = resp.json().get("products", [])
            logger.debug(f"Received {len(products)} products")
            return products
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching products: {e.response.status_code} - {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch products: {type(e).__name__}: {e}")
            return []

    def get_collections(self) -> List[Dict[str, str]]:
        """Get all collections"""
        url = f"{self.store_url}/admin/api/2024-01/custom_collections.json"

        try:
            resp = requests.get(url, headers=self.headers, params={"limit": 250}, timeout=30)
            resp.raise_for_status()
            collections = resp.json().get("custom_collections", [])
            return [{"id": c["id"], "title": c["title"], "handle": c["handle"]} for c in collections]
        except Exception as e:
            logger.error(f"Failed to fetch collections: {e}")
            return []

    def get_collection_products(self, collection_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch products from a specific collection"""
        url = f"{self.store_url}/admin/api/2024-01/collections/{collection_id}/products.json"

        params = {
            "limit": min(limit, 250),
            "fields": "id,title,handle,image,images,body_html,vendor,product_type,tags,published_at,variants",
        }

        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("products", [])
        except Exception as e:
            logger.error(f"Failed to fetch collection products: {e}")
            return []


def format_product_for_pinterest(product: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    """Format Shopify product for Pinterest pin creation"""

    product_url = f"{base_url}/products/{product.get('handle', '')}"

    # Get best image
    images = product.get("images", [])
    main_image = images[0] if images else None
    image_url = main_image.get("src", "") if main_image else ""

    # Extract product info
    title = product.get("title", "")
    body = product.get("body_html", "").replace("<p>", "").replace("</p>", "").strip()[:200]
    product_type = product.get("product_type", "")
    vendor = product.get("vendor", "")
    tags = product.get("tags", "").split(",")[:3] if product.get("tags") else []

    # Price from first variant
    variants = product.get("variants", [])
    price = variants[0].get("price", "") if variants else ""

    return {
        "product_id": product.get("id"),
        "title": title,
        "product_type": product_type,
        "vendor": vendor,
        "description": body,
        "tags": [t.strip() for t in tags if t.strip()],
        "price": price,
        "url": product_url,
        "image_url": image_url,
        "image_alt": f"{title} - {product_type}" if product_type else title,
    }


def get_pinterest_board_mapping() -> Dict[str, List[str]]:
    """Map keywords to actual MeeeShop Pinterest board names (as returned by the API).
    Keys are real board names; values are keywords to match in product title/type/tags.
    """
    return {
        "Cocktail Dresses": ["dress", "gown", "maxi", "midi", "mini"],
        "Puff Sleeve Tops": ["top", "blouse", "shirt", "cami", "tank", "puff"],
        "Kancan USA Jeans": ["jeans", "denim"],
        "Pants & Leggings": ["pants", "leggings", "trousers"],
        "Coats & Jackets": ["coat", "jacket", "blazer", "shacket"],
        "Women's shacket": ["shacket", "shirt jacket"],
        "Loungewear": ["lounge", "pyjama", "pajama", "sweat"],
        "Skirts": ["skirt"],
        "Sweaters": ["sweater", "knit", "cardigan", "pullover"],
        "Womens Cardigans": ["cardigan"],
        "Trendy Backpacks": ["backpack", "bag", "purse", "tote", "handbag"],
        "Spring Outfits": ["spring", "floral", "light"],
        "Winter Outfits": ["winter", "warm", "wool", "fleece"],
        "Edgy fashion": ["edgy", "leather", "moto", "biker"],
        "Luxe Clothing": ["luxe", "luxury", "silk", "satin"],
        "Simple Outfits": ["casual", "simple", "basic", "everyday"],
        "Style Ideas": ["style", "outfit", "ootd"],
        "New Trendy Women Apparel, Shoes, Handbags & more": ["new", "trend"],
    }


def select_board_for_product(product_data: Dict[str, Any]) -> str:
    """Select Pinterest board based on product type/tags. Returns an actual board name."""

    board_map = get_pinterest_board_mapping()

    title = (product_data.get("title") or "").lower()
    product_type = (product_data.get("product_type") or "").lower()
    tags = [t.lower() for t in product_data.get("tags", [])]
    search_text = f"{title} {product_type} {' '.join(tags)}"

    # Check all keywords against combined text
    for board, keywords in board_map.items():
        if any(kw in search_text for kw in keywords):
            return board

    # Default to a high-visibility board that exists in the account
    return "Style Ideas"


def main():
    """Test Shopify client"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    try:
        from secrets_manager import get_secret
        store_url = get_secret("SHOPIFY_STORE_URL")
        access_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    except Exception as _e:
        logger.critical("[secrets] Failed to load Shopify credentials: %s", _e, exc_info=True)
        raise

    if not store_url or not access_token:
        raise ValueError("Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN in secrets.enc")

    client = ShopifyClient(store_url, access_token)

    products = client.get_products(limit=5)
    for p in products:
        formatted = format_product_for_pinterest(p, "https://us.meeeshop.com")
        board = select_board_for_product(formatted)
        print(f"Title: {formatted['title']}")
        print(f"Board: {board}")
        print(f"URL: {formatted['url']}")
        print()


if __name__ == "__main__":
    main()
