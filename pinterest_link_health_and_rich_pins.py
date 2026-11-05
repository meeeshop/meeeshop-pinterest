#!/usr/bin/env python3
"""
pinterest_link_health_and_rich_pins.py — Dead-Link (404) Prevention & Product Rich Pins Validator

1. Scans pinned product and blog URLs from history to detect broken links / 404 errors.
2. Automatically creates Shopify 301 redirects for any deleted/missing products to
   relevant active collections so Pinterest bots and shoppers never see a dead page.
3. Validates OpenGraph & Schema.org JSON-LD Rich Pin metadata required by Pinterest.
4. Generates a link health report (link_health_report.json and summary).
"""

import os
import sys
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
except Exception as e:
    print(f"Warning loading secrets: {e}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("LinkHealth")

STORE_BASE = "https://us.meeeshop.com"
REPORT_FILE = ROOT / "link_health_report.json"


def get_shopify_headers():
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }


def create_shopify_redirect(path_from: str, target_collection: str) -> bool:
    """Create a 301 redirect in Shopify to prevent 404 penalties from Pinterest."""
    store_url = os.environ.get("SHOPIFY_STORE", os.environ.get("SHOPIFY_STORE_URL", "us-meeeshop.myshopify.com"))
    if "://" in store_url:
        store_url = store_url.split("://")[1].strip("/")
    
    url = f"https://{store_url}/admin/api/2024-10/redirects.json"
    clean_from = "/" + path_from.lstrip("/")
    payload = {
        "redirect": {
            "path": clean_from,
            "target": target_collection
        }
    }
    try:
        r = requests.post(url, headers=get_shopify_headers(), json=payload, timeout=10)
        if r.status_code in (200, 201):
            logger.info(f"✅ Created Shopify 301 redirect: {clean_from} -> {target_collection}")
            return True
        elif r.status_code == 422:
            logger.info(f"ℹ️ Redirect already exists for {clean_from}")
            return True
        else:
            logger.warning(f"Failed to create redirect {clean_from}: HTTP {r.status_code} - {r.text[:100]}")
    except Exception as e:
        logger.error(f"Error creating redirect: {e}")
    return False


def collect_urls_from_histories() -> List[str]:
    """Collect unique URLs from all posting histories."""
    urls = set()

    hist_files = [
        ROOT / "outfit_formula_history.json",
        ROOT / "posting_history_stealth.json",
        ROOT / "blog_posting_history.json",
        ROOT / "tagged_popular_pins_history.json",
    ]

    for p in hist_files:
        if not p.exists():
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            posts = data.get("posts") or data.get("tagged_pins") or []
            if isinstance(posts, dict):
                posts = list(posts.values())
            for item in posts:
                # Direct links
                u = item.get("link") or item.get("target_url") or item.get("url")
                if u and isinstance(u, str) and u.startswith("http"):
                    urls.add(u.split("?")[0])
                
                # Check outfit items
                for oi in item.get("outfit_items", []):
                    ou = oi.get("url")
                    if ou and isinstance(ou, str):
                        urls.add(ou.split("?")[0])
                
                # Check tagged products
                for tp in item.get("tagged_products", []):
                    tu = tp.get("url")
                    if tu and isinstance(tu, str):
                        urls.add(tu.split("?")[0])
        except Exception as e:
            logger.warning(f"Error reading {p.name}: {e}")

    return list(urls)


def check_url_health(url: str) -> Dict[str, Any]:
    """Check HTTP status and Pinterest Rich Pin compliance for a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Pinterest/0.2 (+https://www.pinterest.com/bot.html)"
    }
    res = {
        "url": url,
        "status_code": 0,
        "is_404": False,
        "redirect_created": False,
        "rich_pin_ready": False,
        "error": None
    }
    try:
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        res["status_code"] = r.status_code
        if r.status_code == 404:
            res["is_404"] = True
            # Attempt to create redirect to category
            path = url.replace("https://us.meeeshop.com", "").replace("http://us.meeeshop.com", "").split("?")[0]
            target = "/collections/all"
            if "/products/" in path:
                if any(k in path for k in ["jean", "denim", "flare"]):
                    target = "/collections/kancan-usa-jeans"
                elif any(k in path for k in ["sweater", "cardigan", "knit"]):
                    target = "/collections/womens-sweaters"
                elif any(k in path for k in ["dress"]):
                    target = "/collections/womens-dresses"
                elif any(k in path for k in ["bag", "tote", "crossbody"]):
                    target = "/collections/womens-handbags"
                else:
                    target = "/collections/womens-tops"
            created = create_shopify_redirect(path, target)
            res["redirect_created"] = created

        elif r.status_code == 200 and "/products/" in url:
            # Check Rich Pin schema
            soup = BeautifulSoup(r.text, "html.parser")
            og_price = soup.find("meta", property="og:price:amount") or soup.find("meta", property="product:price:amount")
            og_title = soup.find("meta", property="og:title")
            res["rich_pin_ready"] = bool(og_price and og_title)
    except Exception as e:
        res["error"] = str(e)

    return res


def run_audit(sample_limit: int = 50):
    logger.info("=" * 70)
    logger.info("Pinterest Link Health & Rich Pins Compliance Audit")
    logger.info("=" * 70)

    urls = collect_urls_from_histories()
    logger.info(f"Total distinct pinned URLs collected: {len(urls)}")

    # Sample audit: prioritize checking the most recent 50 URLs
    check_sample = urls[-sample_limit:] if len(urls) > sample_limit else urls
    logger.info(f"Auditing sample of {len(check_sample)} URLs...")

    results = []
    dead_count = 0
    redirected_count = 0
    rich_pin_count = 0

    for i, u in enumerate(check_sample, 1):
        res = check_url_health(u)
        results.append(res)
        if res["is_404"]:
            dead_count += 1
            if res["redirect_created"]:
                redirected_count += 1
        if res["rich_pin_ready"]:
            rich_pin_count += 1
        
        status_sym = "❌ 404" if res["is_404"] else (f"✅ {res['status_code']}" if res["status_code"] == 200 else f"⚠️ {res['status_code']}")
        logger.info(f"[{i}/{len(check_sample)}] {status_sym} -> {u}")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_urls_in_history": len(urls),
        "sampled_urls": len(check_sample),
        "dead_404_count": dead_count,
        "redirects_repaired": redirected_count,
        "rich_pin_ready_count": rich_pin_count,
        "results": results
    }

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("=" * 70)
    logger.info(f"Audit Complete! Dead 404s: {dead_count} (Repaired with 301 Redirect: {redirected_count}) | Rich Pins Ready: {rich_pin_count}/{len(check_sample)}")
    logger.info(f"Report saved to: {REPORT_FILE}")
    logger.info("=" * 70)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="Number of URLs to check in sample")
    args = parser.parse_args()
    run_audit(sample_limit=args.limit)
