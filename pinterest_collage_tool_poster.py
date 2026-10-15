"""
pinterest_collage_tool_poster.py — Pinterest Native Collage Creation Tool Automation

Uses Pinterest's official Collage Creation Tool:
https://www.pinterest.com/collage-creation-tool/?ads=true&advertiser_id=549763231328
to build interactive cutout stickers of already-pinned rich pin products into
"Outfit Formula" / "How to Style It" Collages.

Every cutout sticker retains native product attribution and functions as a clickable
shopping element directly within Pinterest's Shuffles & Collage ecosystem.
"""

import os
import sys
import time
import json
import random
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from playwright.sync_api import sync_playwright, Page, BrowserContext

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from secrets_manager import inject_to_env, get_secret
    inject_to_env()
except Exception as e:
    logging.warning(f"[secrets] secrets_manager fallback: {e}")

from stealth_pinterest_poster import StealthPinterestPoster

# Safe UTF-8 console output
sys_stdout = sys.stdout
if hasattr(sys_stdout, "reconfigure"):
    try:
        sys_stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys_stdout)]
)
logger = logging.getLogger("PinterestCollagePoster")

COLLAGE_TOOL_URL = "https://www.pinterest.com/collage-creation-tool/?ads=true&advertiser_id=549763231328"
COLLAGE_HISTORY_FILE = ROOT / "outfit_collage_pins_history.json"


class PinterestCollagePoster:
    """
    Automates the creation of outfit collages using Pinterest's native Collage Creation Tool.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.poster_helper = StealthPinterestPoster(headless=headless)

    def _get_cookies(self) -> List[Dict[str, Any]]:
        return self.poster_helper._get_cookies_dict()

    def _load_history(self) -> Dict[str, Any]:
        if COLLAGE_HISTORY_FILE.exists():
            try:
                with open(COLLAGE_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read {COLLAGE_HISTORY_FILE}: {e}")
        return {"posts": [], "last_run": None}

    def _save_history(self, record: Dict[str, Any]):
        history = self._load_history()
        history["posts"].append(record)
        history["last_run"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(COLLAGE_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            logger.info(f"Recorded collage pin to {COLLAGE_HISTORY_FILE}")
        except Exception as e:
            logger.error(f"Error saving history: {e}")

    def create_outfit_collage(
        self,
        formula: Dict[str, Any],
        items: List[Dict[str, Any]],
        board_name: str,
        dry_run: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Creates an Outfit Formula collage with 4 cutout stickers using the Collage Creation Tool.

        Args:
            formula: Dictionary containing formula metadata (id, title, style, etc.)
            items: List of 4 items with keys (title, role, product_id, pin_id (optional), etc.)
            board_name: Target Pinterest board name.
            dry_run: If True, stops before clicking the final 'Publish' button.

        Returns:
            Dict containing post metadata if successful, None otherwise.
        """
        logger.info(f"🎨 Starting Native Pinterest Collage Creation: '{formula.get('formula_title')}' on Board '{board_name}'")
        cookies = self._get_cookies()
        if not cookies:
            logger.error("No Pinterest authentication cookies available.")
            return None

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--window-size=1400,950'
                ]
            )
            ctx = browser.new_context(
                viewport={'width': 1400, 'height': 950},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York"
            )
            ctx.add_cookies(cookies)
            page = ctx.new_page()

            try:
                logger.info(f"Navigating to Pinterest Collage Creation Tool: {COLLAGE_TOOL_URL}...")
                page.goto(COLLAGE_TOOL_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)

                # Ensure we are on the creation tool page
                if "collage-creation-tool" not in page.url:
                    logger.error(f"Redirected away from collage tool to: {page.url}")
                    browser.close()
                    return None

                # 4-quadrant coordinates on 1400x950 canvas viewport:
                # Top-Left: (460, 370)
                # Top-Right: (700, 370)
                # Bottom-Left: (460, 680)
                # Bottom-Right: (700, 680)
                quadrant_coords = [
                    (460, 370),  # Top-Left: The Top
                    (700, 370),  # Top-Right: The Bag
                    (460, 680),  # Bottom-Left: The Denim
                    (700, 680),  # Bottom-Right: The Footwear
                ]

                added_count = 0
                for i, item in enumerate(items[:4]):
                    dest_x, dest_y = quadrant_coords[i] if i < len(quadrant_coords) else (580, 530)
                    success = self._add_item_cutout(page, item, dest_x, dest_y)
                    if success:
                        added_count += 1
                    time.sleep(1.5)

                logger.info(f"Total cutouts added to collage canvas: {added_count}/4")
                if added_count == 0:
                    logger.error("Failed to add any cutout stickers to canvas.")
                    browser.close()
                    return None

                # Save screenshot of assembled outfit collage canvas
                scratch_dir = ROOT / "scratch"
                scratch_dir.mkdir(exist_ok=True)
                canvas_shot = scratch_dir / f"collage_canvas_{formula.get('formula_id', 'outfit')}_{int(time.time())}.png"
                page.screenshot(path=str(canvas_shot))
                logger.info(f"Saved canvas preview to {canvas_shot}")

                # Click Next to open Publish metadata screen
                next_btn = page.locator("button:has-text('Next')")
                if not next_btn.is_enabled():
                    page.wait_for_timeout(2000)

                if not next_btn.is_enabled():
                    logger.error("Next button remains disabled.")
                    browser.close()
                    return None

                logger.info("Clicking 'Next' to open publish metadata screen...")
                next_btn.click(force=True)
                page.wait_for_timeout(4000)

                # Fill metadata: Title, Description, Alt Text, Board
                pin_title = formula.get("seo_title", f"{formula.get('formula_title')} - Outfit Guide | MeeeShop")[:100]
                pin_desc = formula.get("seo_description", f"How to style {formula.get('formula_title')}. Tap on any piece to shop the look directly from MeeeShop.")[:500]
                alt_text = f"Outfit Formula Collage featuring {', '.join([it.get('title', '') for it in items[:4]])} from MeeeShop US boutique."

                # Title
                title_input = page.locator("#CollageBuilderMetadataTitle, input[placeholder*='Add a title' i]").first
                if title_input.is_visible():
                    title_input.click(force=True)
                    title_input.fill(pin_title)
                    logger.info(f"Filled Title: {pin_title[:50]}...")

                # Description
                desc_input = page.locator("#CollageBuilderMetadataDescription, textarea[placeholder*='Add a description' i]").first
                if desc_input.is_visible():
                    desc_input.click(force=True)
                    desc_input.fill(pin_desc)
                    logger.info("Filled Description")

                # Alt Text
                alt_input = page.locator("#CollageBuilderMetadataAltText, textarea[placeholder*='Add visual details' i]").first
                if alt_input.is_visible():
                    alt_input.click(force=True)
                    alt_input.fill(alt_text[:450])
                    logger.info("Filled Alt Text")

                # Board Selection
                board_selected = self.poster_helper._select_board_ui(page, board_name)
                logger.info(f"Board selection result: {board_selected}")

                ready_shot = scratch_dir / f"collage_ready_{formula.get('formula_id', 'outfit')}_{int(time.time())}.png"
                page.screenshot(path=str(ready_shot))
                logger.info(f"Saved ready-to-publish screen to {ready_shot}")

                if dry_run:
                    logger.info("DRY-RUN mode active. Skipping final Publish button click.")
                    browser.close()
                    return {
                        "status": "dry_run",
                        "formula_id": formula.get("formula_id"),
                        "title": pin_title,
                        "board": board_name,
                        "items_count": added_count,
                        "canvas_image": str(canvas_shot),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                # Publish Pin!
                publish_btn = page.locator("button:has-text('Publish'), div[role='button']:has-text('Publish')").first
                if publish_btn.is_visible() and publish_btn.is_enabled():
                    logger.info("🚀 Clicking 'Publish' button...")
                    publish_btn.click(force=True)
                    page.wait_for_timeout(8000)

                    pub_shot = scratch_dir / f"collage_published_{int(time.time())}.png"
                    page.screenshot(path=str(pub_shot))
                    logger.info(f"Saved publish result screenshot to {pub_shot}")

                    pin_id = self._extract_created_pin_id(page)
                    pin_url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else None

                    record = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "formula_id": formula.get("formula_id"),
                        "formula_title": formula.get("formula_title"),
                        "pin_url": pin_url,
                        "pin_id": pin_id,
                        "board": board_name,
                        "title": pin_title,
                        "type": "native_collage",
                        "canvas_preview": str(canvas_shot),
                        "cutout_items": [
                            {"role": it.get("role"), "title": it.get("title"), "product_id": it.get("id"), "pin_id": it.get("pin_id")}
                            for it in items[:added_count]
                        ]
                    }
                    self._save_history(record)
                    logger.info(f"🎉 Native Outfit Collage Pin Published Successfully! URL: {pin_url or 'Live on Board'}")
                    browser.close()
                    return record
                else:
                    logger.error("Publish button not found or not enabled.")
                    browser.close()
                    return None

            except Exception as e:
                logger.error(f"Error during collage creation: {e}", exc_info=True)
                err_shot = ROOT / "scratch" / "collage_error.png"
                try:
                    page.screenshot(path=str(err_shot))
                    logger.info(f"Saved error screenshot to {err_shot}")
                except Exception:
                    pass
                browser.close()
                return None

    def _add_item_cutout(self, page: Page, item: Dict[str, Any], dest_x: float, dest_y: float) -> bool:
        """
        Searches for a product (via Pin ID, product title, or keyword),
        opens the Snip Tool, selects the garment cutout, adds to collage, and positions it.
        """
        role = item.get("role", "ITEM")
        title = item.get("title", "")
        pin_id = item.get("pin_id")

        search_query = str(pin_id) if pin_id else self._clean_search_title(title, role)
        logger.info(f"🔍 Searching for {role} using query: '{search_query}'")

        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # Find search box in discoverability panel
            search_input = page.locator("[data-test-id='discoverability-panel'] [data-test-id='collage-search-box-input']").first
            search_input.click(force=True)
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            search_input.fill(search_query)
            search_input.press("Enter")
            page.wait_for_timeout(3500)

            # Find result images in panel
            panel = page.locator("[data-test-id='discoverability-panel']")
            imgs = panel.locator("img")
            clicked = False
            for i in range(imgs.count()):
                img = imgs.nth(i)
                if img.is_visible():
                    logger.info(f"Clicking search result img #{i} to open Snip Tool...")
                    img.click(force=True)
                    clicked = True
                    break

            if not clicked:
                fallback_query = role.replace("THE ", "").lower()
                logger.warning(f"No visible image found for '{search_query}'. Trying fallback: '{fallback_query}'")
                search_input.click(force=True)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                search_input.fill(fallback_query)
                search_input.press("Enter")
                page.wait_for_timeout(3500)
                for i in range(imgs.count()):
                    img = imgs.nth(i)
                    if img.is_visible():
                        img.click(force=True)
                        clicked = True
                        break

            if not clicked:
                logger.error(f"Failed to find and click an image for {role}")
                return False

            page.wait_for_timeout(3000)

            # Check if Snip Tool opened
            try:
                page.wait_for_selector("text='Snip tool'", timeout=8000)
            except Exception:
                logger.warning("Snip tool did not open.")
                return False

            # In Snip Tool: click Select all or click image center to ensure cutout selection
            select_all_btn = page.locator("button[aria-label='Select all']").first
            if select_all_btn.is_visible():
                select_all_btn.click(force=True)
                page.wait_for_timeout(1500)
            else:
                snip_img = page.locator("div:has-text('Snip tool') ~ div img, div:has-text('Click on objects') img").first
                if snip_img.is_visible():
                    box = snip_img.bounding_box()
                    if box:
                        page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                        page.wait_for_timeout(2000)

            # Click Add Pin to the collage button
            add_btn = page.locator("button[aria-label='Add Pin to the collage'], button:has-text('Add to collage')").first
            add_btn.click(force=True)
            logger.info(f"✓ Added cutout sticker for {role} to collage canvas")
            page.wait_for_timeout(3500)

            # Reposition cutout on canvas
            canvas_cx, canvas_cy = 580, 530
            logger.info(f"Repositioning {role} cutout from ({canvas_cx}, {canvas_cy}) to ({dest_x}, {dest_y})...")
            page.mouse.move(canvas_cx, canvas_cy)
            page.mouse.down()
            page.mouse.move(dest_x, dest_y, steps=8)
            page.mouse.up()
            page.wait_for_timeout(1000)

            # Click neutral area to deselect
            page.mouse.click(360, 220)
            page.wait_for_timeout(800)

            return True

        except Exception as e:
            logger.warning(f"Error adding cutout for {role}: {e}")
            return False

    def _clean_search_title(self, title: str, role: str) -> str:
        """Simplifies a product title into high-matching 2-3 word search query."""
        clean = title.split(" - ")[0].split(" | ")[0]
        words = clean.split()
        if len(words) > 3:
            return " ".join(words[:3])
        return clean or role.replace("THE ", "").lower()

    def _extract_created_pin_id(self, page: Page) -> Optional[str]:
        """Tries to extract pin ID from page URL or confirmation links."""
        url = page.url
        if "/pin/" in url:
            parts = url.split("/pin/")
            if len(parts) > 1:
                return parts[1].strip("/").split("/")[0]

        pin_link = page.locator("a[href*='/pin/']").first
        if pin_link.is_visible():
            href = pin_link.get_attribute("href") or ""
            if "/pin/" in href:
                return href.split("/pin/")[1].strip("/").split("/")[0]

        return None


def run_native_collage_workflow(
    formula_name: str = "auto",
    pins_count: int = 1,
    dry_run: bool = False
) -> bool:
    """
    Top-level function to run the native Pinterest Collage Tool workflow.
    Picks in-stock Shopify products matching the formula preset, creates cutouts,
    assembles the 4-item outfit collage, and publishes to Pinterest.
    """
    logger.info("=" * 70)
    logger.info(f"Pinterest Native Collage Tool Pipeline (Dry-Run: {dry_run}, Formula: {formula_name})")
    logger.info("=" * 70)

    from pinterest_outfit_formula import (
        OUTFIT_FORMULAS,
        ShopifyClient,
        OutfitCatalog,
        load_history,
        get_recently_used_ids,
        generate_outfit_seo
    )

    store_url = get_secret("SHOPIFY_STORE_URL")
    access_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    if not store_url or not access_token:
        logger.critical("Missing SHOPIFY_STORE_URL or SHOPIFY_ACCESS_TOKEN")
        return False

    client = ShopifyClient(store_url, access_token)
    catalog = OutfitCatalog(client)
    catalog.load_catalog()

    history = load_history()
    recent_ids = get_recently_used_ids(history, days=5)
    all_formula_keys = list(OUTFIT_FORMULAS.keys())

    poster = PinterestCollagePoster(headless=True)
    success_count = 0

    for pin_idx in range(pins_count):
        logger.info(f"\n[Collage Pin #{pin_idx + 1}/{pins_count}]")
        if formula_name != "auto" and formula_name in OUTFIT_FORMULAS:
            formula = OUTFIT_FORMULAS[formula_name]
        else:
            chosen_key = random.choice(all_formula_keys)
            formula = OUTFIT_FORMULAS[chosen_key]

        logger.info(f"[FORMULA] Selected: '{formula['title']}' ({formula['id']})")
        session_used_ids = set()
        outfit_items = []

        for slot in formula["slots"]:
            item = catalog.pick_item_for_slot(slot, session_used_ids, recent_ids)
            if item:
                item_copy = dict(item)
                item_copy["role"] = slot["role_label"]
                outfit_items.append(item_copy)

        if len(outfit_items) < 3:
            logger.error("Not enough in-stock items available to build collage.")
            continue

        seo = generate_outfit_seo(formula, outfit_items)
        board_name = formula.get("board_name", "Casual Outfits")

        res = poster.create_outfit_collage(
            formula={
                "formula_id": formula["id"],
                "formula_title": formula["title"],
                "seo_title": seo["title"],
                "seo_description": seo["description"],
            },
            items=outfit_items,
            board_name=board_name,
            dry_run=dry_run
        )

        if res:
            success_count += 1

        if pin_idx < pins_count - 1:
            wait_sec = random.randint(20, 40)
            logger.info(f"Waiting {wait_sec}s before next collage pin...")
            time.sleep(wait_sec)

    logger.info(f"\n[DONE] Native Collage workflow complete! {success_count}/{pins_count} pins processed.")
    return success_count > 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pinterest Native Collage Creation Tool Automation")
    parser.add_argument("--dry-run", action="store_true", help="Run up to publish screen without hitting publish")
    parser.add_argument("--apply", action="store_true", help="Publish live to Pinterest")
    parser.add_argument("--formula", default="auto", help="Preset formula ID (or 'auto')")
    parser.add_argument("--pins-count", type=int, default=1, help="Number of collage pins to create")
    args = parser.parse_args()

    is_dry_run = args.dry_run or not args.apply
    ok = run_native_collage_workflow(
        formula_name=args.formula,
        pins_count=args.pins_count,
        dry_run=is_dry_run
    )
    sys.exit(0 if ok else 1)
