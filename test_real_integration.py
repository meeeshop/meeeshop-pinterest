#!/usr/bin/env python3
"""
test_real_integration.py — End-to-end Pinterest automation test
Tests: 1 Shopify product image + URL + 1 YouTube video from last 2-3 days
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environments
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

youtube_env = Path(__file__).parent.parent / "meeeshop-youtube" / ".env"
if youtube_env.exists():
    load_dotenv(youtube_env)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("test_real_integration.log"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


class RealIntegrationTest:
    """Test Pinterest automation with real Shopify products & YouTube videos"""

    def __init__(self):
        self.test_results = {
            "test_name": "Real Integration Test",
            "start_time": datetime.now().isoformat(),
            "steps": [],
            "success": False,
            "product_data": None,
            "video_data": None,
            "errors": [],
        }

    def log_step(self, step: int, title: str, status: str, details: str = ""):
        """Log test step"""
        icon = "✓" if status == "OK" else "✗" if status == "FAILED" else "⚠"
        logger.info(f"\n{icon} Step {step}: {title}")
        logger.info(f"   Status: {status}")
        if details:
            for line in details.split("\n"):
                logger.info(f"   {line}")

        self.test_results["steps"].append({
            "step": step,
            "title": title,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        })

    def verify_credentials(self) -> bool:
        """Step 1: Verify all credentials are set"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 1: VERIFY CREDENTIALS")
        logger.info("=" * 70)

        creds = {
            "PINTEREST_EMAIL": os.getenv("PINTEREST_EMAIL"),
            "SHOPIFY_STORE_URL": os.getenv("SHOPIFY_STORE_URL"),
            "SHOPIFY_ACCESS_TOKEN": os.getenv("SHOPIFY_ACCESS_TOKEN"),
            "STORE_BASE_URL": os.getenv("STORE_BASE_URL"),
            "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
            "YOUTUBE_CHANNEL_ID": os.getenv("YOUTUBE_CHANNEL_ID"),
        }

        missing = [k for k, v in creds.items() if not v]
        if missing:
            details = f"Missing: {', '.join(missing)}"
            self.log_step(1, "Verify Credentials", "FAILED", details)
            self.test_results["errors"].append(f"Missing credentials: {missing}")
            return False

        details = f"All credentials loaded:\n"
        for k, v in creds.items():
            masked = v[:10] + "***" if v else "MISSING"
            details += f"{k}: {masked}\n"

        self.log_step(1, "Verify Credentials", "OK", details)
        return True

    def fetch_shopify_products(self) -> Optional[Dict[str, Any]]:
        """Step 2: Fetch one Shopify product with image"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 2: FETCH SHOPIFY PRODUCT")
        logger.info("=" * 70)

        try:
            import requests

            store_url = os.getenv("SHOPIFY_STORE_URL").rstrip("/")
            access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

            headers = {
                "X-Shopify-Access-Token": access_token,
                "Content-Type": "application/json",
            }

            url = f"{store_url}/admin/api/2024-01/products.json"
            params = {
                "limit": 5,
                "status": "active",
                "published_status": "published",
                "fields": "id,title,handle,image,images,body_html,vendor,product_type,tags,variants",
            }

            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()

            products = resp.json().get("products", [])
            if not products:
                self.log_step(2, "Fetch Shopify Product", "FAILED", "No products found")
                return None

            # Pick first product with images
            product = None
            for p in products:
                if p.get("images"):
                    product = p
                    break

            if not product:
                self.log_step(2, "Fetch Shopify Product", "FAILED", "No products with images found")
                return None

            # Format product data
            images = product.get("images", [])
            variants = product.get("variants", [])

            product_data = {
                "id": product.get("id"),
                "title": product.get("title"),
                "handle": product.get("handle"),
                "type": product.get("product_type"),
                "vendor": product.get("vendor"),
                "description": product.get("body_html", "")[:200],
                "tags": product.get("tags", "").split(",")[:3] if product.get("tags") else [],
                "price": variants[0].get("price") if variants else "N/A",
                "image_url": images[0].get("src") if images else None,
                "image_alt": images[0].get("alt", product.get("title")) if images else product.get("title"),
                "product_url": f"{os.getenv('STORE_BASE_URL')}/products/{product.get('handle')}",
            }

            self.test_results["product_data"] = product_data

            details = (
                f"Product: {product_data['title']}\n"
                f"Type: {product_data['type']}\n"
                f"Price: ${product_data['price']}\n"
                f"Image: {product_data['image_url'][:50]}...\n"
                f"URL: {product_data['product_url']}"
            )

            self.log_step(2, "Fetch Shopify Product", "OK", details)
            return product_data

        except Exception as e:
            self.log_step(2, "Fetch Shopify Product", "FAILED", str(e))
            self.test_results["errors"].append(f"Shopify fetch: {e}")
            return None

    def fetch_youtube_video(self) -> Optional[Dict[str, Any]]:
        """Step 3: Fetch 1 YouTube video from last 2-3 days"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 3: FETCH YOUTUBE VIDEO (Last 2-3 Days)")
        logger.info("=" * 70)

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            import googleapiclient.discovery

            channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
            refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
            client_id = os.getenv("YOUTUBE_CLIENT_ID")
            client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

            if not all([channel_id, refresh_token, client_id, client_secret]):
                self.log_step(3, "Fetch YouTube Video", "FAILED", "Missing YouTube credentials")
                return None

            # Create credentials from refresh token
            creds_info = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "type": "authorized_user",
            }

            creds = Credentials.from_authorized_user_info(creds_info)
            if creds.expired:
                creds.refresh(Request())

            # Get YouTube service
            youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

            # Search for videos from last 2-3 days
            since = (datetime.now() - timedelta(days=3)).isoformat() + "Z"

            request = youtube.search().list(
                part="snippet",
                channelId=channel_id,
                type="video",
                order="date",
                maxResults=5,
                publishedAfter=since,
            )

            response = request.execute()
            videos = response.get("items", [])

            if not videos:
                self.log_step(3, "Fetch YouTube Video", "FAILED", "No videos from last 3 days")
                return None

            # Get first video details
            video = videos[0]
            snippet = video.get("snippet", {})
            video_id = video.get("id", {}).get("videoId")

            video_data = {
                "id": video_id,
                "title": snippet.get("title"),
                "description": snippet.get("description", "")[:200],
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "published_at": snippet.get("publishedAt"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }

            self.test_results["video_data"] = video_data

            published_date = snippet.get("publishedAt", "").split("T")[0]
            details = (
                f"Video: {video_data['title']}\n"
                f"ID: {video_id}\n"
                f"Published: {published_date}\n"
                f"URL: {video_data['url']}\n"
                f"Thumbnail: {video_data['thumbnail'][:50]}..."
            )

            self.log_step(3, "Fetch YouTube Video", "OK", details)
            return video_data

        except Exception as e:
            self.log_step(3, "Fetch YouTube Video", "FAILED", str(e))
            self.test_results["errors"].append(f"YouTube fetch: {e}")
            return None

    def generate_pinterest_content(self, product_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Step 4: Generate Pinterest content (title, description, hashtags)"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 4: GENERATE PINTEREST CONTENT")
        logger.info("=" * 70)

        try:
            from content_generator import (
                generate_pinterest_title,
                generate_pinterest_description,
            )
            from board_mapping import get_board_for_product

            title = generate_pinterest_title(product_data)
            description = generate_pinterest_description(product_data, "Women's Fashion")
            board = get_board_for_product(product_data.get("title", ""), product_data.get("type", ""))

            content = {
                "title": title,
                "description": description,
                "board": board,
                "tags": product_data.get("tags", []),
            }

            details = (
                f"Title: {content['title']}\n"
                f"Description: {content['description']}\n"
                f"Board: {content['board']}\n"
                f"Tags: {', '.join(content['tags'])}"
            )

            self.log_step(4, "Generate Pinterest Content", "OK", details)
            return content

        except Exception as e:
            self.log_step(4, "Generate Pinterest Content", "FAILED", str(e))
            self.test_results["errors"].append(f"Content generation: {e}")
            return None

    def validate_image_url(self, url: str) -> bool:
        """Step 5: Validate product image is accessible"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 5: VALIDATE PRODUCT IMAGE")
        logger.info("=" * 70)

        try:
            import requests

            resp = requests.head(url, timeout=10, allow_redirects=True)
            is_valid = resp.status_code == 200

            status = "OK" if is_valid else "FAILED"
            details = (
                f"URL: {url[:60]}...\n"
                f"Status Code: {resp.status_code}\n"
                f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}"
            )

            self.log_step(5, "Validate Product Image", status, details)
            return is_valid

        except Exception as e:
            self.log_step(5, "Validate Product Image", "FAILED", str(e))
            self.test_results["errors"].append(f"Image validation: {e}")
            return False

    def check_pinterest_boards(self) -> bool:
        """Step 6: Verify Pinterest boards exist"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 6: CHECK PINTEREST BOARDS")
        logger.info("=" * 70)

        try:
            from board_mapping import MEEESHOP_BOARDS, HIGH_TRAFFIC_BOARDS

            details = f"Total boards: {len(MEEESHOP_BOARDS)}\n"
            details += f"High-traffic boards: {len(HIGH_TRAFFIC_BOARDS)}\n\n"
            details += f"Sample high-traffic boards:\n"
            for board in HIGH_TRAFFIC_BOARDS:
                details += f"  - {board}\n"

            self.log_step(6, "Check Pinterest Boards", "OK", details)
            return True

        except Exception as e:
            self.log_step(6, "Check Pinterest Boards", "FAILED", str(e))
            self.test_results["errors"].append(f"Board check: {e}")
            return False

    def verify_pinterest_cookies(self) -> bool:
        """Step 7: Check if Pinterest cookies are saved"""
        logger.info("\n" + "=" * 70)
        logger.info("STEP 7: VERIFY PINTEREST COOKIES")
        logger.info("=" * 70)

        try:
            cookies_file = Path(__file__).parent / ".pinterest_cookies"

            if cookies_file.exists():
                size = cookies_file.stat().st_size
                mod_time = datetime.fromtimestamp(cookies_file.stat().st_mtime)
                age_days = (datetime.now() - mod_time).days

                details = (
                    f"Cookies file: {cookies_file.name}\n"
                    f"Size: {size} bytes\n"
                    f"Last updated: {age_days} days ago\n"
                    f"Status: VALID" if age_days < 30 else "Status: EXPIRED (>30 days)"
                )

                status = "OK" if age_days < 30 else "⚠"
                self.log_step(7, "Verify Pinterest Cookies", status, details)
                return True
            else:
                details = (
                    "Cookies file not found.\n"
                    "Run: python credentials_manager.py to generate cookies\n"
                    "or use email/password from .env"
                )
                self.log_step(7, "Verify Pinterest Cookies", "⚠", details)
                return False

        except Exception as e:
            self.log_step(7, "Verify Pinterest Cookies", "FAILED", str(e))
            return False

    def save_test_results(self):
        """Save test results to JSON"""
        self.test_results["end_time"] = datetime.now().isoformat()
        self.test_results["success"] = len(self.test_results["errors"]) == 0

        results_file = Path(__file__).parent / "test_real_integration_results.json"
        results_file.write_text(json.dumps(self.test_results, indent=2, default=str))

        logger.info(f"\n✓ Results saved: {results_file}")

    def run(self):
        """Run all test steps"""
        logger.info("\n" + "=" * 70)
        logger.info("🚀 PINTEREST REAL INTEGRATION TEST")
        logger.info("=" * 70)
        logger.info(f"Start time: {datetime.now()}")

        steps = [
            (self.verify_credentials, "Verify credentials are set"),
            (self.fetch_shopify_products, "Fetch 1 product from Shopify"),
            (self.fetch_youtube_video, "Fetch 1 video from YouTube"),
            (lambda: self.generate_pinterest_content(self.test_results["product_data"]) if self.test_results["product_data"] else None, "Generate Pinterest content"),
            (lambda: self.validate_image_url(self.test_results["product_data"]["image_url"]) if self.test_results["product_data"] else False, "Validate image URL"),
            (self.check_pinterest_boards, "Check Pinterest boards"),
            (self.verify_pinterest_cookies, "Verify Pinterest cookies"),
        ]

        step_num = 1
        for step_func, step_title in steps:
            try:
                result = step_func()
                if result is None:
                    logger.warning(f"Step {step_num} returned None")
            except Exception as e:
                logger.error(f"Step {step_num} error: {e}")
                self.test_results["errors"].append(f"Step {step_num}: {e}")
            step_num += 1

        self.save_test_results()

        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Total steps: {len(self.test_results['steps'])}")
        logger.info(f"Passed: {len([s for s in self.test_results['steps'] if s['status'] == 'OK'])}")
        logger.info(f"Failed: {len(self.test_results['errors'])}")

        if self.test_results["product_data"]:
            logger.info(f"\n✓ Product: {self.test_results['product_data']['title']}")
        if self.test_results["video_data"]:
            logger.info(f"✓ Video: {self.test_results['video_data']['title']}")

        if self.test_results["errors"]:
            logger.info("\n❌ ERRORS:")
            for error in self.test_results["errors"]:
                logger.info(f"  - {error}")
        else:
            logger.info("\n✅ ALL TESTS PASSED!")

        logger.info(f"\nResults file: test_real_integration_results.json")


if __name__ == "__main__":
    test = RealIntegrationTest()
    test.run()
