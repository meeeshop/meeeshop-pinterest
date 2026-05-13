#!/usr/bin/env python3
"""
debug_pinterest_posting.py — Step-by-step debugging of Pinterest posting
Tests each step independently to pinpoint where posting fails
"""

import os
import time
import logging
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Load env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

def test_login():
    """Test 1: Can we log in with saved cookies?"""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Login with Saved Cookies")
    logger.info("="*70)

    from credentials_manager import CredentialsManager

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)

    try:
        if CredentialsManager.load_cookies(driver):
            driver.get("https://pinterest.com")
            time.sleep(3)

            # Check for homefeed
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='homefeed']"))
                )
                logger.info("✓ Login successful - homefeed detected")
                return driver
            except Exception as e:
                logger.error(f"✗ Homefeed not detected: {e}")
                # Try to detect if we're on a different page
                current_url = driver.current_url
                logger.info(f"  Current URL: {current_url}")
                page_title = driver.title
                logger.info(f"  Page title: {page_title}")
                driver.save_screenshot("debug_login_fail.png")
                driver.quit()
                return None
        else:
            logger.error("✗ Failed to load cookies")
            driver.quit()
            return None
    except Exception as e:
        logger.error(f"✗ Login test crashed: {e}")
        driver.quit()
        return None

def test_boards(driver):
    """Test 2: Can we fetch boards?"""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Fetch Boards")
    logger.info("="*70)

    try:
        driver.get("https://pinterest.com/me/boards/")
        time.sleep(3)

        logger.info(f"  Current URL: {driver.current_url}")
        logger.info(f"  Page title: {driver.title}")

        # Look for board links
        board_elements = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/board/']"))
        )

        logger.info(f"✓ Found {len(board_elements)} board elements")

        boards = {}
        for elem in board_elements:
            board_name = elem.get_attribute("aria-label")
            board_url = elem.get_attribute("href")

            if board_name and board_url and "/board/" in board_url:
                board_id = board_url.split("/board/")[-1].split("/")[0]
                boards[board_name] = board_id
                logger.info(f"  - {board_name}: {board_id}")

        if boards:
            logger.info(f"✓ Successfully fetched {len(boards)} boards")
            return boards
        else:
            logger.error("✗ No boards found with expected structure")
            driver.save_screenshot("debug_boards_fail.png")
            return None

    except Exception as e:
        logger.error(f"✗ Board fetch failed: {e}")
        driver.save_screenshot("debug_boards_error.png")
        return None

def test_pin_creation_page(driver):
    """Test 3: Can we access the pin creation page?"""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: Access Pin Creation Page")
    logger.info("="*70)

    try:
        driver.get("https://pinterest.com/pin/create/")
        time.sleep(3)

        logger.info(f"  Current URL: {driver.current_url}")
        logger.info(f"  Page title: {driver.title}")

        # Look for file input
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        logger.info(f"  Found {len(file_inputs)} file input(s)")

        if file_inputs:
            logger.info("✓ File input found")
            return True
        else:
            logger.error("✗ File input not found on pin creation page")

            # Debug: list all inputs
            all_inputs = driver.find_elements(By.TAG_NAME, "input")
            logger.info(f"  Total inputs on page: {len(all_inputs)}")
            for i, inp in enumerate(all_inputs[:5]):
                logger.info(f"    Input {i}: type={inp.get_attribute('type')}, name={inp.get_attribute('name')}")

            driver.save_screenshot("debug_pin_create_fail.png")
            return False

    except Exception as e:
        logger.error(f"✗ Pin creation page access failed: {e}")
        driver.save_screenshot("debug_pin_create_error.png")
        return False

def test_image_upload(driver, image_path):
    """Test 4: Can we upload an image?"""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Upload Image")
    logger.info("="*70)

    try:
        if not Path(image_path).exists():
            logger.error(f"✗ Image file not found: {image_path}")
            return False

        # Make sure we're on the create page
        driver.get("https://pinterest.com/pin/create/")
        time.sleep(2)

        # Find and fill file input
        file_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
        )

        file_path = Path(image_path).resolve()
        logger.info(f"  Uploading: {file_path}")

        file_input.send_keys(str(file_path))
        time.sleep(4)  # Wait for upload to process

        # Check if upload succeeded
        title_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[placeholder*='title' i]"))
        )

        logger.info("✓ Image uploaded and title field appeared")
        return True

    except Exception as e:
        logger.error(f"✗ Image upload failed: {e}")
        driver.save_screenshot("debug_upload_fail.png")
        return False

def main():
    logger.info("\n" + "="*70)
    logger.info("🔍 PINTEREST POSTING DEBUG — Step-by-Step Analysis")
    logger.info("="*70)

    # Test 1: Login
    driver = test_login()
    if not driver:
        logger.error("\n❌ FAILED AT STEP 1: Login")
        return False

    # Test 2: Boards
    boards = test_boards(driver)
    if not boards:
        logger.error("\n❌ FAILED AT STEP 2: Fetch Boards")
        driver.quit()
        return False

    # Test 3: Pin creation page
    if not test_pin_creation_page(driver):
        logger.error("\n❌ FAILED AT STEP 3: Pin Creation Page")
        driver.quit()
        return False

    # Test 4: Image upload (download a test image first)
    logger.info("\n" + "="*70)
    logger.info("Preparing test image...")
    logger.info("="*70)

    try:
        import requests
        import tempfile

        # Use a small test image from Shopify
        image_url = "https://cdn.shopify.com/s/files/1/0608/4103/3098/products/image_2024-05-15_085005-removebg-preview_500x500.png"
        logger.info(f"  Downloading test image from: {image_url}")

        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(resp.content)
            image_path = f.name

        logger.info(f"  Test image saved: {image_path}")

        if test_image_upload(driver, image_path):
            logger.info("\n✓ All basic steps passed!")
            logger.info("  The posting should work. Trying a full post...")

            # Try to actually post
            try:
                textarea_inputs = driver.find_elements(By.TAG_NAME, "textarea")
                if len(textarea_inputs) >= 1:
                    textarea_inputs[0].send_keys("Test Pin from Debug Script")
                    logger.info("  Title entered")

                time.sleep(2)
                driver.save_screenshot("debug_before_save.png")
                logger.info("  Screenshot saved: debug_before_save.png")

            except Exception as e:
                logger.error(f"  Error filling form: {e}")
        else:
            logger.error("\n❌ FAILED AT STEP 4: Image Upload")

        # Cleanup
        Path(image_path).unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"✗ Test image preparation failed: {e}")

    finally:
        driver.quit()

    logger.info("\n" + "="*70)
    logger.info("DEBUG COMPLETE")
    logger.info("Screenshots saved if errors occurred (debug_*.png)")
    logger.info("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n⏹ Debug cancelled")
