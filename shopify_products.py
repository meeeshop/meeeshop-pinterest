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


import re
import time

def parse_gid(gid: str) -> int:
    """Extract integer ID from Shopify GID string."""
    if not gid:
        return 0
    match = re.search(r'/(\d+)$', gid)
    return int(match.group(1)) if match else 0


def map_graphql_product(node: Dict[str, Any]) -> Dict[str, Any]:
    """Map Shopify GraphQL Product node to REST-like dictionary format"""
    images = [{"src": edge["node"]["url"]} for edge in node.get("images", {}).get("edges", [])]
    variants = []
    for edge in node.get("variants", {}).get("edges", []):
        v = edge["node"]
        variants.append({
            "id": parse_gid(v.get("id")),
            "price": v.get("price"),
            "inventory_quantity": v.get("inventoryQuantity", 0),
            "inventory_policy": (v.get("inventoryPolicy") or "").lower(),
        })

    return {
        "id": parse_gid(node.get("id")),
        "title": node.get("title"),
        "handle": node.get("handle"),
        "body_html": node.get("bodyHtml") or "",
        "vendor": node.get("vendor"),
        "product_type": node.get("productType"),
        "tags": ", ".join(node.get("tags") or []),
        "published_at": node.get("publishedAt"),
        "images": images,
        "image": images[0] if images else None,
        "variants": variants,
    }


class ShopifyClient:
    """Fetch products from Shopify store using GraphQL Admin API"""

    def __init__(self, store_url: str, access_token: str):
        clean_url = store_url.replace("https://", "").replace("http://", "").rstrip("/")
        self.store_url = f"https://{clean_url}"
        self.graphql_url = f"{self.store_url}/admin/api/2024-01/graphql.json"
        self.access_token = access_token
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    def run_graphql(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Run GraphQL Admin API query with rate-limiting retry."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        for attempt in range(5):
            try:
                resp = requests.post(self.graphql_url, headers=self.headers, json=payload, timeout=30)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2.0))
                    time.sleep(retry_after)
                    continue
                resp.raise_for_status()
                result = resp.json()
                if "errors" in result:
                    logger.error(f"[GraphQL] Errors in response: {result['errors']}")
                return result
            except requests.exceptions.RequestException as e:
                if attempt < 4:
                    time.sleep(2.0 ** attempt)
                else:
                    raise e
        raise RuntimeError("GraphQL request failed after 5 attempts")
    def get_products(
        self,
        collection: Optional[str] = None,
        limit: int = 50,
        status: str = "active",
        published: bool = True,
        product_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch products from store using GraphQL"""
        query_parts = []
        if status:
            query_parts.append(f"status:{status}")
        if published:
            query_parts.append("published_status:published")
        if product_type:
            # Escape quotes in product type
            safe_type = product_type.replace("'", "\\'")
            query_parts.append(f"product_type:'{safe_type}'")

        query_str = " AND ".join(query_parts) if query_parts else None

        query = """
        query ($first: Int!, $queryStr: String) {
          products(first: $first, query: $queryStr) {
            edges {
              node {
                id
                title
                handle
                vendor
                productType
                tags
                publishedAt
                bodyHtml
                images(first: 10) {
                  edges {
                    node {
                      url
                    }
                  }
                }
                variants(first: 50) {
                  edges {
                    node {
                      id
                      price
                      inventoryQuantity
                      inventoryPolicy
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            variables = {"first": min(limit, 250), "queryStr": query_str}
            res = self.run_graphql(query, variables)
            edges = res.get("data", {}).get("products", {}).get("edges", [])
            products = [map_graphql_product(edge["node"]) for edge in edges]
            logger.debug(f"Received {len(products)} products via GraphQL")
            return products
        except Exception as e:
            logger.error(f"Failed to fetch products: {e}")
            return []

    def get_all_products(self, status: str = "active", published: bool = True) -> List[Dict[str, Any]]:
        """Fetch all active products with pagination using GraphQL"""
        query_parts = []
        if status:
            query_parts.append(f"status:{status}")
        if published:
            query_parts.append("published_status:published")

        query_str = " AND ".join(query_parts) if query_parts else None

        query = """
        query ($first: Int!, $after: String, $queryStr: String) {
          products(first: $first, after: $after, query: $queryStr) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                id
                title
                handle
                vendor
                productType
                tags
                publishedAt
                bodyHtml
                images(first: 10) {
                  edges {
                    node {
                      url
                    }
                  }
                }
                variants(first: 50) {
                  edges {
                    node {
                      id
                      price
                      inventoryQuantity
                      inventoryPolicy
                    }
                  }
                }
              }
            }
          }
        }
        """
        products = []
        has_next = True
        cursor = None

        while has_next:
            try:
                variables = {"first": 250, "after": cursor, "queryStr": query_str}
                res = self.run_graphql(query, variables)
                data = res.get("data", {}).get("products", {})
                edges = data.get("edges", [])
                for edge in edges:
                    products.append(map_graphql_product(edge["node"]))

                page_info = data.get("pageInfo", {})
                has_next = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")
            except Exception as e:
                logger.error(f"Error in paginated product fetch: {e}")
                break

        return products

    def get_collections(self) -> List[Dict[str, str]]:
        """Get all collections using GraphQL"""
        query = """
        query ($first: Int!) {
          collections(first: $first) {
            edges {
              node {
                id
                title
                handle
              }
            }
          }
        }
        """
        try:
            res = self.run_graphql(query, {"first": 250})
            edges = res.get("data", {}).get("collections", {}).get("edges", [])
            return [
                {
                    "id": str(parse_gid(edge["node"]["id"])),
                    "title": edge["node"]["title"],
                    "handle": edge["node"]["handle"],
                }
                for edge in edges
            ]
        except Exception as e:
            logger.error(f"Failed to fetch collections: {e}")
            return []

    def get_collection_products(self, collection_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch products from a specific collection using GraphQL"""
        gql_id = f"gid://shopify/Collection/{collection_id}"
        query = """
        query ($id: ID!, $first: Int!) {
          collection(id: $id) {
            products(first: $first) {
              edges {
                node {
                  id
                  title
                  handle
                  vendor
                  productType
                  tags
                  publishedAt
                  bodyHtml
                  images(first: 10) {
                    edges {
                      node {
                        url
                      }
                    }
                  }
                  variants(first: 50) {
                    edges {
                      node {
                        id
                        price
                        inventoryQuantity
                        inventoryPolicy
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            res = self.run_graphql(query, {"id": gql_id, "first": min(limit, 250)})
            edges = res.get("data", {}).get("collection", {}).get("products", {}).get("edges", [])
            return [map_graphql_product(edge["node"]) for edge in edges]
        except Exception as e:
            logger.error(f"Failed to fetch collection products: {e}")
            return []

    def get_product_by_handle(self, handle: str) -> Optional[Dict[str, Any]]:
        """Fetch a single product by its handle using GraphQL"""
        query = """
        query ($queryStr: String!) {
          products(first: 1, query: $queryStr) {
            edges {
              node {
                id
                title
                handle
                vendor
                productType
                tags
                publishedAt
                bodyHtml
                images(first: 10) {
                  edges {
                    node {
                      url
                    }
                  }
                }
                variants(first: 50) {
                  edges {
                    node {
                      id
                      price
                      inventoryQuantity
                      inventoryPolicy
                    }
                  }
                }
              }
            }
          }
        }
        """
        try:
            res = self.run_graphql(query, {"queryStr": f"handle:{handle}"})
            edges = res.get("data", {}).get("products", {}).get("edges", [])
            return map_graphql_product(edges[0]["node"]) if edges else None
        except Exception as e:
            logger.error(f"Failed to fetch product by handle {handle}: {e}")
            return None



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
    import re
    title = (product_data.get("title") or "").lower()
    product_type = (product_data.get("product_type") or "").lower()
    tags = [t.lower() for t in product_data.get("tags", [])]
    search_text = f"{title} {product_type} {' '.join(tags)}"

    category_mappings = [
        (["backpack", "bag", "purse", "tote", "handbag", "crossbody", "clutch", "satchel", "wallet", "pouch", "duffel", "hobo"], "bag"),
        (["dress", "gown", "midi", "maxi", "mini"], "dress"),
        (["top", "blouse", "tank", "shirt", "cami"], "top"),
        (["jeans", "denim", "pants", "legging"], "pants"),
        (["jacket", "coat", "shacket", "blazer"], "jacket"),
        (["cardigan"], "cardigan"),
        (["sweater", "knit", "pullover"], "sweater"),
        (["skirt"], "skirt"),
        (["shoe", "boot", "flat", "heel", "sandal"], "shoe"),
        (["jumpsuit", "romper"], "jumpsuit")
    ]
    
    boundary_keys = {"top", "flat"}
    matched_cat = None
    
    for keywords, category_key_val in category_mappings:
        for kw in keywords:
            if kw in boundary_keys:
                if kw == "top":
                    if re.search(r'\btops?(?!-handle|-loading|-heavy)\b', search_text):
                        matched_cat = category_key_val
                        break
                else:
                    if re.search(r'\b' + re.escape(kw) + r's?\b', search_text):
                        matched_cat = category_key_val
                        break
            else:
                if kw in search_text:
                    matched_cat = category_key_val
                    break
        if matched_cat:
            break

    category_to_board = {
        "bag": "Trendy Backpacks",
        "dress": "Cocktail Dresses",
        "top": "Puff Sleeve Tops",
        "pants": "Pants & Leggings",
        "jacket": "Coats & Jackets",
        "cardigan": "Womens Cardigans",
        "sweater": "Sweaters",
        "skirt": "Skirts",
        "shoe": "Footwear",
        "jumpsuit": "Style Ideas"
    }

    if matched_cat and matched_cat in category_to_board:
        return category_to_board[matched_cat]

    board_map = get_pinterest_board_mapping()
    for board, keywords in board_map.items():
        if any(kw in search_text for kw in keywords):
            return board

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
