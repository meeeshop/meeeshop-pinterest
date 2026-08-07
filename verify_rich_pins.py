"""
verify_rich_pins.py — MeeeShop Shopify Rich Pins Validator Diagnostic

Verifies that live Shopify product pages output complete OpenGraph and schema.org JSON-LD
metadata required for Pinterest Product Rich Pins (price, currency, availability, title, image).
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from secrets_manager import inject_to_env
inject_to_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verify_rich_pins")


def check_product_url_rich_pins(url: str) -> Dict[str, Any]:
    """Check a single product URL for OpenGraph & Schema.org Rich Pin metadata."""
    results = {
        "url": url,
        "opengraph": {},
        "schema_org": {},
        "missing_fields": [],
        "rich_pin_status": "UNKNOWN",
        "recommendations": []
    }

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Pinterest/0.1"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. Inspect OpenGraph Tags
        og_tags = {}
        for tag in soup.find_all("meta"):
            prop = tag.get("property") or tag.get("name")
            content = tag.get("content")
            if prop and content:
                og_tags[prop] = content

        og_price = (
            og_tags.get("og:price:amount") or
            og_tags.get("product:price:amount") or
            og_tags.get("price")
        )
        og_currency = (
            og_tags.get("og:price:currency") or
            og_tags.get("product:price:currency") or
            og_tags.get("currency") or "USD"
        )
        og_avail = (
            og_tags.get("og:availability") or
            og_tags.get("product:availability")
        )
        og_title = og_tags.get("og:title")
        og_image = og_tags.get("og:image") or og_tags.get("og:image:secure_url")

        results["opengraph"] = {
            "title": og_title,
            "price_amount": og_price,
            "currency": og_currency,
            "availability": og_avail,
            "image": og_image
        }

        # 2. Inspect Schema.org JSON-LD
        schema_data = None
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Product":
                            schema_data = item
                            break
                elif isinstance(data, dict) and data.get("@type") == "Product":
                    schema_data = data
                    break
            except Exception:
                continue

        if schema_data:
            offers = schema_data.get("offers", {})
            if isinstance(offers, list) and offers:
                offers = offers[0]
            results["schema_org"] = {
                "name": schema_data.get("name"),
                "image": schema_data.get("image"),
                "price": offers.get("price") if isinstance(offers, dict) else None,
                "currency": offers.get("priceCurrency") if isinstance(offers, dict) else None,
                "availability": offers.get("availability") if isinstance(offers, dict) else None
            }

        # 3. Evaluate Rich Pin Requirements
        missing = []
        if not og_title and not results["schema_org"].get("name"):
            missing.append("Title (og:title or schema:name)")
        if not og_price and not results["schema_org"].get("price"):
            missing.append("Price Amount (og:price:amount or schema:price)")
        if not og_image and not results["schema_org"].get("image"):
            missing.append("Image (og:image or schema:image)")

        results["missing_fields"] = missing

        if not missing:
            results["rich_pin_status"] = "PASSED ✅"
            results["recommendations"].append("Product URL contains full Rich Pin metadata!")
        elif len(missing) == 1:
            results["rich_pin_status"] = "WARNING ⚠️"
            results["recommendations"].append(f"Missing minor tag: {missing[0]}")
        else:
            results["rich_pin_status"] = "FAILED ❌"
            results["recommendations"].append(f"Missing required tags: {', '.join(missing)}")

    except Exception as e:
        logger.error(f"Error validating {url}: {e}")
        results["rich_pin_status"] = "ERROR ❌"
        results["recommendations"].append(str(e))

    return results


def run_rich_pins_diagnostic() -> Dict[str, Any]:
    """Run Rich Pins check across products fetched from Shopify."""
    from shopify_products import ShopifyClient

    store_url = os.getenv("SHOPIFY_STORE_URL", "https://us.meeeshop.com")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    client = ShopifyClient(store_url=store_url, access_token=access_token)
    products = client.get_products(limit=5)

    if not products:
        logger.warning("No Shopify products retrieved for Rich Pins check.")
        return {"status": "NO_PRODUCTS_FOUND"}

    logger.info(f"🔎 Testing {len(products)} products for Pinterest Rich Pins compliance...")
    report = {"checked_at": requests.utils.default_user_agent(), "products": []}

    for prod in products:
        handle = prod.get("handle")
        store_url = os.getenv("SHOPIFY_STORE_URL", "https://us.meeeshop.com").rstrip("/")
        if handle:
            url = f"{store_url}/products/{handle}"
        else:
            url = store_url

        res = check_product_url_rich_pins(url)
        res["product_title"] = prod.get("title")
        res["product_id"] = prod.get("id")
        report["products"].append(res)
        logger.info(f"Product '{prod.get('title')[:30]}' -> Status: {res['rich_pin_status']}")

    output_path = Path(__file__).parent / "rich_pins_report.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Report written to: {output_path}")
    return report


if __name__ == "__main__":
    run_rich_pins_diagnostic()
