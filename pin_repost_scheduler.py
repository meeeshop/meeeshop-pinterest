#!/usr/bin/env python3
"""Re‑pin scheduler for Pinterest.

This script runs every 12 h (via GitHub Actions) and looks for pins that were
posted more than 24 h ago.  It republishes them to a secondary board defined in
``board_mapping.SECONDARY_BOARDS``.  If a pin has already been re‑pinned once,
it will be skipped to avoid excessive duplication.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

_log = logging.getLogger(__name__)
try:
    from secrets_manager import inject_to_env
    inject_to_env()
    _log.info("[secrets] inject_to_env() succeeded")
except Exception as _e:
    _log.critical("[secrets] inject_to_env() FAILED: %s", _e, exc_info=True)
    raise

from pinterest_client import PinterestClient
from board_mapping import SECONDARY_BOARDS, MEEESHOP_BOARDS

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent / "posting_history.json"
REPIN_INTERVAL_HOURS = 24


def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return {"posts": [], "board_last_used": {}, "daily_count": 0, "last_post_time": None}


def save_history(history: dict):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def should_repin(post: dict, history: dict) -> bool:
    """Return True if the pin is older than 24 h and hasn't been re‑pinned."""
    posted_time = datetime.fromisoformat(post["timestamp"])
    if datetime.utcnow() - posted_time < timedelta(hours=REPIN_INTERVAL_HOURS):
        return False
    # Check if already re‑pinned
    for p in history["posts"]:
        if p.get("original_id") == post["product_id"] and p.get("board") != post["board"]:
            return False
    return True


def run_repin(use_video: bool = False):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    pinterest_email = os.getenv("PINTEREST_EMAIL")
    pinterest_password = os.getenv("PINTEREST_PASSWORD")
    if not pinterest_email or not pinterest_password:
        raise ValueError("Missing Pinterest credentials")

    pinterest = PinterestClient(pinterest_email, pinterest_password, headless=True)
    if not pinterest.login():
        logger.error("Pinterest login failed")
        return

    boards = pinterest.fetch_boards()
    history = load_history()
    updated = False

    for post in list(history["posts"]):
        if not should_repin(post, history):
            continue
        board = SECONDARY_BOARDS.get(post["board"], [b for b in MEEESHOP_BOARDS if b not in post["board"]])
        if not board:
            continue
        target_board = board[0]
        # Re‑pin using the same content
        success = pinterest.create_pin(
            image_or_video_path=post.get("image_path"),
            title=post.get("title"),
            description=post.get("description"),
            board_name=target_board,
            url=post.get("url"),
            alt_text=post.get("alt_text"),
        )
        if success:
            logger.info(f"Re‑pinned product {post['product_id']} to {target_board}")
            post["original_id"] = post["product_id"]
            post["board"] = target_board
            post["timestamp"] = datetime.utcnow().isoformat()
            updated = True

    if updated:
        save_history(history)
    pinterest.close()


if __name__ == "__main__":
    run_repin()
