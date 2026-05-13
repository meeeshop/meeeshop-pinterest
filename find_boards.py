#!/usr/bin/env python3
"""
find_boards.py — Extract board information from boards page
Uses JavaScript to find boards on the page
"""

import time
import logging
import json
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from credentials_manager import CredentialsManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)

options = webdriver.ChromeOptions()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--start-maximized")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

try:
    logger.info("🔍 FINDING PINTEREST BOARDS")
    logger.info("=" * 70)

    if not CredentialsManager.load_cookies(driver):
        logger.error("Failed to load cookies")
        exit(1)

    driver.get("https://pinterest.com")
    time.sleep(3)

    logger.info("✓ Navigating to boards page...")
    driver.get("https://pinterest.com/me/boards/")
    time.sleep(4)

    logger.info(f"Current URL: {driver.current_url}")
    logger.info(f"Page title: {driver.title}")

    # Method 1: Find all elements with aria-label that might be boards
    logger.info("\n📋 Method 1: Looking for aria-labels...")
    script1 = """
    return Array.from(document.querySelectorAll('[aria-label]'))
        .map(el => ({
            tag: el.tagName,
            aria: el.getAttribute('aria-label'),
            href: el.getAttribute('href'),
            class: el.getAttribute('class')?.substring(0, 50)
        }))
        .filter(el => el.aria && (el.aria.toLowerCase().includes('board') || el.href?.includes('board')))
        .slice(0, 20);
    """

    result1 = driver.execute_script(script1)
    if result1:
        logger.info(f"Found {len(result1)} elements with board-related aria-labels:")
        for item in result1:
            logger.info(f"  - {item['tag']}: aria='{item['aria']}'")
            logger.info(f"    href: {item['href']}")
    else:
        logger.info("  No board aria-labels found")

    # Method 2: Look for anchor tags with board in href
    logger.info("\n📋 Method 2: Looking for links with '/board/' in href...")
    script2 = """
    return Array.from(document.querySelectorAll('a[href*="/board/"]'))
        .map(el => ({
            aria: el.getAttribute('aria-label'),
            href: el.getAttribute('href'),
            text: el.textContent?.trim().substring(0, 50)
        }))
        .slice(0, 20);
    """

    result2 = driver.execute_script(script2)
    if result2:
        logger.info(f"Found {len(result2)} links with /board/ in href:")
        for item in result2:
            logger.info(f"  - aria: '{item['aria']}'")
            logger.info(f"    href: {item['href']}")
            logger.info(f"    text: '{item['text']}'")
    else:
        logger.info("  No /board/ links found")

    # Method 3: Look for data-testid variations
    logger.info("\n📋 Method 3: Looking for data-testid elements...")
    script3 = """
    return Array.from(document.querySelectorAll('[data-testid*="board"], [data-test-id*="board"]'))
        .map(el => ({
            tag: el.tagName,
            testid: el.getAttribute('data-testid') || el.getAttribute('data-test-id'),
            aria: el.getAttribute('aria-label'),
            href: el.getAttribute('href'),
            text: el.textContent?.trim().substring(0, 50)
        }))
        .slice(0, 20);
    """

    result3 = driver.execute_script(script3)
    if result3:
        logger.info(f"Found {len(result3)} data-testid/data-test-id elements:")
        for item in result3:
            logger.info(f"  - {item['tag']}: testid='{item['testid']}'")
            logger.info(f"    aria: '{item['aria']}'")
    else:
        logger.info("  No data-testid/data-test-id elements found")

    # Method 4: Look at overall page structure
    logger.info("\n📋 Method 4: Page structure analysis...")
    script4 = """
    const pageInfo = {
        url: window.location.href,
        title: document.title,
        totalLinks: document.querySelectorAll('a').length,
        totalButtons: document.querySelectorAll('button').length,
        boardLinks: Array.from(document.querySelectorAll('a')).filter(a => a.href.includes('board')).length,
        hasCreateButton: !!document.querySelector('[aria-label*="Create"], [aria-label*="create"]'),
        bodyClasses: document.body.className
    };
    return pageInfo;
    """

    result4 = driver.execute_script(script4)
    logger.info(f"  Total links: {result4['totalLinks']}")
    logger.info(f"  Total buttons: {result4['totalButtons']}")
    logger.info(f"  Board-related links: {result4['boardLinks']}")
    logger.info(f"  Has create button: {result4['hasCreateButton']}")

    # Save screenshot
    driver.save_screenshot("boards_debug.png")
    logger.info("\n📸 Screenshot saved: boards_debug.png")

    logger.info("\n" + "=" * 70)
    if result2:
        logger.info("✓ Found boards! You can now post.")
    else:
        logger.info("⚠ No boards found on page")
        logger.info("  This might be a navigation/permission issue")

finally:
    driver.quit()
