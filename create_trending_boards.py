#!/usr/bin/env python3
"""
create_trending_boards.py — Auto-create high-demand Pinterest boards dynamically using AI.

Identifies high-converting Pinterest search terms that women shoppers in the USA look for,
combines them with our in-stock product types, and automatically creates missing boards on Pinterest.
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

sys.path.insert(0, str(Path(__file__).parent))

from secrets_manager import inject_to_env, get_secret
inject_to_env()

from pinterest_client import PinterestClient
from shopify_products import ShopifyClient
from ai_client import generate
from keyword_engine import SEASONAL_KEYWORDS
from board_mapping import MEEESHOP_BOARDS, match_live_board, CATEGORY_TO_BOARDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

DYNAMIC_BOARDS_FILE = Path(__file__).parent / "dynamic_boards.json"
MAX_NEW_BOARDS_PER_RUN = 1
MIN_DAYS_BETWEEN_BOARD_CREATION = 14


def fetch_in_stock_product_types(shopify: ShopifyClient) -> List[str]:
    products = shopify.get_all_products(status="active")
    types = set()
    for p in products:
        # Check if in stock
        if any(v.get("inventory_quantity", 0) >= 1 for v in p.get("variants", [])):
            ptype = p.get("product_type")
            if ptype:
                types.add(ptype)
    return list(types)


def generate_trending_boards(product_types: List[str]) -> List[Dict[str, str]]:
    from datetime import datetime, timedelta
    # Look 45 days (6-8 weeks) ahead so new boards are indexed before US seasonal search peaks
    target_date = datetime.now() + timedelta(days=45)
    month = target_date.month
    seasonal = SEASONAL_KEYWORDS.get(month, SEASONAL_KEYWORDS[8])
    trends = ", ".join(seasonal["keywords"])
    
    valid_categories = list(CATEGORY_TO_BOARDS.keys())
    
    prompt = f"""
We want to create trending Pinterest boards for women's fashion in the USA (targeting seasonal searches 6-8 weeks ahead) based on these available product types in our store: {', '.join(product_types)}.
Upcoming seasonal trends: {trends}

Generate {MAX_NEW_BOARDS_PER_RUN + 2} trending Pinterest board names and detailed SEO descriptions (250-400 chars) that combine our product types with the upcoming seasonal trends.
Rules for board names:
- Clean 2-4 word US shopper search phrase (e.g., "Holiday Party Dresses", "Cozy Fall Sweaters", "Spring Wedding Guest Dresses").
- NO hashtags (#), NO emojis, NO punctuation clutter.
Also, assign each board to ONE of these exact base categories: {', '.join(valid_categories)}.

Respond STRICTLY with a valid JSON array in this exact format, with no markdown formatting or backticks:
[
  {{"name": "Board Name Here", "description": "Detailed SEO description...", "category": "one_of_the_base_categories"}}
]
"""
    try:
        response = generate(prompt, max_tokens=800, temperature=0.7)
        if not response:
            logger.error("AI generation failed.")
            return []
        
        # Parse JSON
        start = response.find('[')
        end = response.rfind(']')
        if start != -1 and end != -1:
            json_str = response[start:end+1]
            boards = json.loads(json_str)
            
            valid_boards = []
            for b in boards:
                if "name" in b and "description" in b and "category" in b:
                    if b["category"] in valid_categories:
                        valid_boards.append(b)
                    else:
                        b["category"] = "default"
                        valid_boards.append(b)
            return valid_boards
        else:
            logger.error(f"Could not find JSON array in response: {response}")
            return []
    except Exception as e:
        logger.error(f"Error parsing AI response: {e}", exc_info=True)
        return []


def update_dynamic_boards_file(new_boards: List[Dict[str, str]]):
    dynamic_boards = {}
    if DYNAMIC_BOARDS_FILE.exists():
        try:
            dynamic_boards = json.loads(DYNAMIC_BOARDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    for b in new_boards:
        cat = b["category"]
        name = b["name"]
        if cat not in dynamic_boards:
            dynamic_boards[cat] = []
        if name not in dynamic_boards[cat]:
            dynamic_boards[cat].append(name)
            
    if new_boards:
        from datetime import datetime, timezone
        dynamic_boards["_last_created_at"] = datetime.now(timezone.utc).isoformat()

    DYNAMIC_BOARDS_FILE.write_text(json.dumps(dynamic_boards, indent=2), encoding="utf-8")
    logger.info(f"Updated {DYNAMIC_BOARDS_FILE.name}")


def seed_new_board(board_id: str, board_name: str, category: str, target_pins: int = 6) -> int:
    """
    Immediately seed a newly created board with 5-8 relevant in-stock catalog repins
    from _products so the board crosses Pinterest's indexing threshold instead of sitting at 0 pins.
    """
    try:
        from stealth_products_board_saver import StealthProductsBoardSaver
        import time, random
        saver = StealthProductsBoardSaver(headless=True)
        if not saver.initialize_session():
            logger.warning(f"Could not initialize StealthProductsBoardSaver to seed '{board_name}'")
            return 0
        catalog_pins = saver.discover_catalog_pins_from_products_board(max_pins=120)
        if not catalog_pins:
            return 0
        cat_kw = (category or "").lower()
        name_words = [w.lower() for w in board_name.split() if len(w) > 3]
        matching = [
            p for p in catalog_pins
            if cat_kw in f"{p.get('title', '')} {p.get('category_group', '')}".lower()
            or any(w in p.get("title", "").lower() for w in name_words)
        ]
        pool = matching if len(matching) >= target_pins else (matching + [p for p in catalog_pins if p not in matching])
        seeded = 0
        for item in pool[:target_pins]:
            ok, _ = saver.repin_catalog_product(item=item, target_board_id=str(board_id), target_board_name=board_name)
            if ok:
                seeded += 1
                time.sleep(random.uniform(4.0, 8.0))
        logger.info(f"🌱 Seeded newly created board '{board_name}' with {seeded}/{target_pins} catalog pins.")
        return seeded
    except Exception as e:
        logger.warning(f"Board seeding note for '{board_name}': {e}")
        return 0


def sync_and_create_trending_boards(dry_run: bool = False) -> Tuple[List[str], List[str]]:
    logger.info("=" * 70)
    logger.info(f"🔍 CHECKING & CREATING USA TRENDING BOARDS (Dry Run: {dry_run})")
    logger.info("=" * 70)

    shopify_url = get_secret("SHOPIFY_STORE_URL")
    shopify_token = get_secret("SHOPIFY_ACCESS_TOKEN")
    
    shopify = ShopifyClient(shopify_url, shopify_token)
    in_stock_types = fetch_in_stock_product_types(shopify)
    logger.info(f"Found {len(in_stock_types)} in-stock product types.")
    
    if not in_stock_types:
        logger.warning("No in-stock products found. Cannot generate trending boards.")
        return [], []
        
    generated_boards = generate_trending_boards(in_stock_types)
    if not generated_boards:
        logger.error("No valid boards generated by AI.")
        return [], []
        
    client = PinterestClient()
    live_boards = []

    if not dry_run:
        if not client.login():
            logger.error("Failed to authenticate with Pinterest API")
            raise RuntimeError("Pinterest login failed")
        live_boards = client.fetch_boards()
    else:
        live_boards = [{"name": b, "id": f"mock_{i}", "pin_count": 20} for i, b in enumerate(MEEESHOP_BOARDS)]
        if DYNAMIC_BOARDS_FILE.exists():
            try:
                dyn = json.loads(DYNAMIC_BOARDS_FILE.read_text(encoding="utf-8"))
                for k, b_list in dyn.items():
                    if isinstance(b_list, list):
                        for name in b_list:
                            live_boards.append({"name": name, "id": f"mock_dyn_{name}", "pin_count": 20})
            except Exception:
                pass

    # Guardrail 1: Do not create new boards if >= 3 existing boards are empty or thin (< 15 pins)
    thin_boards = [b for b in live_boards if b.get("pin_count") is not None and b.get("pin_count", 0) < 15]
    if len(thin_boards) >= 3:
        logger.info(f"⏸️ Skipping new board creation: {len(thin_boards)} existing boards still have < 15 pins. Fill existing boards first.")
        return [], []

    # Guardrail 2: Enforce 14-day cooldown between new board creations (~1-2/month max)
    if DYNAMIC_BOARDS_FILE.exists():
        try:
            from datetime import datetime, timezone
            dyn_meta = json.loads(DYNAMIC_BOARDS_FILE.read_text(encoding="utf-8"))
            last_created = dyn_meta.get("_last_created_at")
            if last_created:
                dt_last = datetime.fromisoformat(last_created.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - dt_last).days < MIN_DAYS_BETWEEN_BOARD_CREATION:
                    logger.info(f"⏸️ Skipping new board creation: within {MIN_DAYS_BETWEEN_BOARD_CREATION}-day cooldown (last created: {last_created}).")
                    return [], []
        except Exception:
            pass

    created = []
    existing = []
    boards_to_save = []

    for b in generated_boards:
        if len(created) >= MAX_NEW_BOARDS_PER_RUN:
            logger.info(f"Reached max new boards per run limit ({MAX_NEW_BOARDS_PER_RUN}). Skipping remaining.")
            break
            
        name = b["name"]
        desc = b["description"]
        
        matched = match_live_board(name, live_boards)
        if matched:
            logger.info(f"✓ Board already exists: '{matched.get('name')}' (ID: {matched.get('id')})")
            existing.append(name)
        else:
            if dry_run:
                logger.info(f"[DRY RUN] Would create missing board: '{name}' (Category: {b['category']})")
                logger.info(f"          Description: {desc[:80]}...")
                created.append(name)
                boards_to_save.append(b)
            else:
                logger.info(f"Creating missing trending board: '{name}'...")
                success, board_info = client.create_board(name=name, description=desc)
                if success and board_info:
                    new_bid = board_info.get('id')
                    logger.info(f"✓ Created board successfully: '{name}' (ID: {new_bid})")
                    created.append(name)
                    boards_to_save.append(b)
                    if new_bid:
                        seed_new_board(board_id=str(new_bid), board_name=name, category=b.get("category", ""), target_pins=6)
                else:
                    logger.error(f"✗ Failed to create board: '{name}'")
                    
    if boards_to_save:
        update_dynamic_boards_file(boards_to_save)

    logger.info("=" * 70)
    logger.info(f"Summary: {len(existing)} existing boards, {len(created)} new boards {'simulated' if dry_run else 'created'}")
    logger.info("=" * 70)

    return created, existing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create missing USA trending boards on Pinterest")
    parser.add_argument("--dry-run", action="store_true", help="Simulate board creation without applying changes")
    args = parser.parse_args()

    sync_and_create_trending_boards(dry_run=args.dry_run)

