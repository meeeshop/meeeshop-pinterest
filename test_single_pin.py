"""
Test script: Post one product image pin and one video rich pin to Pinterest.
Uses refactored py3-pinterest client for direct API communication.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pinterest_client import PinterestClient
from content_generator import generate_content_package
from youtube_video_downloader import YouTubeVideoDownloader

load_dotenv()

# Test configuration
TEST_PRODUCT_ID = "gid://shopify/Product/1"  # Example product ID
TEST_PRODUCT_CATEGORY = "Women's Fashion"
TEST_YOUTUBE_URL = "https://www.youtube.com/shorts/dQw4w9WgXcQ"  # Example short
TARGET_BOARD_NAME = None  # Will be selected based on category

# Image and video paths
TEST_IMAGE_PATH = "test_product.jpg"
TEST_VIDEO_PATH = "test_video.mp4"


def test_image_pin():
    """Test posting a product image pin."""
    print("\n" + "="*60)
    print("TEST 1: Product Image Pin")
    print("="*60)

    try:
        client = PinterestClient()

        # Step 1: Login
        print("\n[1/4] Logging in to Pinterest...")
        if not client.login():
            print("[FAILED] Login failed")
            return False
        print("[OK] Login successful")

        # Step 2: Fetch boards
        print("\n[2/4] Fetching boards...")
        boards = client.fetch_boards()
        if not boards:
            print("[FAILED] No boards found")
            return False

        # Find target board based on category keywords
        category_keywords = ["women", "fashion", "apparel", "clothing", "style"]
        target_board = None
        for board in boards:
            board_name_lower = board['name'].lower()
            if any(kw in board_name_lower for kw in category_keywords):
                target_board = board
                break

        # Fallback to first board if no match
        if not target_board:
            target_board = boards[0]

        print(f"[OK] Selected board: {target_board['name']} (ID: {target_board['id']})")

        # Step 3: Generate content
        print("\n[3/4] Generating pin content...")
        try:
            content = generate_content_package(
                product_id=TEST_PRODUCT_ID,
                product_name="Test Product",
                product_price="$29.99",
                product_category="Women's Fashion",
                image_url="https://example.com/product.jpg"
            )
            print("[OK] Content generated")
            print(f"  Title: {content.get('title', 'N/A')[:50]}...")
            print(f"  Description: {content.get('description', 'N/A')[:50]}...")
            print(f"  Alt text: {content.get('pin_alt_text', 'N/A')[:50]}...")
        except Exception as e:
            print(f"[WARN] Content generation failed: {e}")
            print("  Using fallback content")
            content = {
                'title': 'Test Product Pin',
                'description': 'Test product description for Pinterest',
                'pin_alt_text': 'Product image test'
            }

        # Step 4: Create pin
        print("\n[4/4] Creating pin on Pinterest...")
        success, result = client.create_pin(
            image_path=TEST_IMAGE_PATH,
            title=content.get('title', 'Test Product'),
            description=content.get('description', 'Test product'),
            board_id=target_board['id'],
            url="https://meeeshop.com/products/test",
            alt_text=content.get('pin_alt_text', 'Product image')
        )

        if success:
            print(f"[OK] Image pin created successfully!")
            print(f"  Pin ID: {result}")
            return True
        else:
            print(f"[FAILED] Failed to create image pin: {result}")
            return False

    except Exception as e:
        print(f"[FAILED] Error in test_image_pin: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_pin():
    """Test posting a video rich pin."""
    print("\n" + "="*60)
    print("TEST 2: Video Rich Pin")
    print("="*60)

    try:
        client = PinterestClient()

        # Step 1: Login
        print("\n[1/5] Logging in to Pinterest...")
        if not client.login():
            print("[FAILED] Login failed")
            return False
        print("[OK] Login successful")

        # Step 2: Fetch boards
        print("\n[2/5] Fetching boards...")
        boards = client.fetch_boards()
        if not boards:
            print("[FAILED] No boards found")
            return False

        # Find target board based on category keywords
        category_keywords = ["women", "fashion", "apparel", "clothing", "style", "video", "content"]
        target_board = None
        for board in boards:
            board_name_lower = board['name'].lower()
            if any(kw in board_name_lower for kw in category_keywords):
                target_board = board
                break

        # Fallback to first board if no match
        if not target_board:
            target_board = boards[0]

        print(f"[OK] Selected board: {target_board['name']} (ID: {target_board['id']})")

        # Step 3: Download YouTube video
        print("\n[3/5] Downloading video from YouTube...")
        print(f"  URL: {TEST_YOUTUBE_URL}")

        if not os.path.exists(TEST_VIDEO_PATH):
            try:
                downloader = YouTubeVideoDownloader()
                video_path = downloader.download_video(TEST_YOUTUBE_URL)
                if not video_path:
                    print("[WARN] Video download failed, skipping video pin test")
                    return False
                print(f"[OK] Video downloaded: {video_path}")
                TEST_VIDEO_PATH = str(video_path)
            except Exception as e:
                print(f"[WARN] Video download error: {e}")
                print("  Skipping video pin test")
                return False
        else:
            print(f"[OK] Video file already exists: {TEST_VIDEO_PATH}")

        # Step 4: Generate content
        print("\n[4/5] Generating video pin content...")
        try:
            content = generate_content_package(
                product_id=TEST_PRODUCT_ID,
                product_name="Test Product Video",
                product_price="$29.99",
                product_category="Women's Fashion",
                image_url="https://example.com/product.jpg"
            )
            print("[OK] Content generated")
        except Exception as e:
            print(f"[WARN] Content generation failed: {e}")
            content = {
                'title': 'Test Product Video Pin',
                'description': 'Video demonstration of test product',
                'pin_alt_text': 'Product video demonstration'
            }

        # Step 5: Create video pin
        print("\n[5/5] Creating video pin on Pinterest...")
        success, result = client.create_pin(
            image_path=TEST_VIDEO_PATH,
            title=content.get('title', 'Test Product Video'),
            description=content.get('description', 'Product video'),
            board_id=target_board['id'],
            url="https://meeeshop.com/products/test",
            alt_text=content.get('pin_alt_text', 'Product video')
        )

        if success:
            print(f"[OK] Video pin created successfully!")
            print(f"  Pin ID: {result}")
            return True
        else:
            print(f"[FAILED] Failed to create video pin: {result}")
            return False

    except Exception as e:
        print(f"[FAILED] Error in test_video_pin: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PINTEREST PIN POSTING TEST")
    print("="*60)
    print(f"Board target: {TARGET_BOARD_NAME}")
    print(f"Product ID: {TEST_PRODUCT_ID}")
    print(f"YouTube URL: {TEST_YOUTUBE_URL}")

    # Check test files exist
    if not os.path.exists(TEST_IMAGE_PATH):
        print(f"\n[WARN] Test image not found: {TEST_IMAGE_PATH}")
        print("  Create a test product image first")

    # Run tests
    results = {
        'Image Pin': test_image_pin(),
        'Video Pin': test_video_pin()
    }

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "[PASSED]" if passed else "[FAILED]"
        print(f"{test_name}: {status}")

    total_passed = sum(1 for v in results.values() if v)
    total_tests = len(results)
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")

    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
