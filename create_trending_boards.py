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
    from datetime import datetime
    month = datetime.now().month
    seasonal = SEASONAL_KEYWORDS.get(month, SEASONAL_KEYWORDS[8])
    trends = ", ".join(seasonal["keywords"])
    
    valid_categories = list(CATEGORY_TO_BOARDS.keys())
    
    prompt = f"""
We want to create trending Pinterest boards for women's fashion in the USA based on these available product types in our store: {', '.join(product_types)}.
Current seasonal trends: {trends}

Generate {MAX_NEW_BOARDS_PER_RUN + 2} trending Pinterest board names and detailed SEO descriptions (300-400 chars) that combine our product types with the seasonal trends.
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
                    logger.info(f"✓ Created board successfully: '{name}' (ID: {board_info.get('id')})")
                    created.append(name)
                    boards_to_save.append(b)
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

