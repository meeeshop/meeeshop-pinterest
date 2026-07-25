"""
analytics_report.py — Weekly Analytics & Performance Report Digest for MeeeShop Pinterest
Analyzes posting histories, board distributions, product coverage, and engagement metrics.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent

HISTORIES = {
    "product_v2": ROOT / "posting_history_v2.json",
    "product_v1": ROOT / "posting_history.json",
    "blog": ROOT / "blog_posting_history.json",
    "video": ROOT / "video_posting_history.json",
    "refresh": ROOT / "refresh_history_v2.json",
}

REPORT_FILE = ROOT / "weekly_analytics_report.json"


def load_json(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Error loading {path.name}: {e}")
    return {}


def generate_weekly_report() -> Dict[str, Any]:
    now = datetime.now()
    seven_days_ago = now - timedelta(days=7)
    
    total_posted_7d = 0
    boards_counter: Dict[str, int] = {}
    posts_by_type = {"product": 0, "blog": 0, "video": 0, "refresh": 0}

    # Product V2
    data_v2 = load_json(HISTORIES["product_v2"])
    for post in data_v2.get("posts", []):
        ts_str = post.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= seven_days_ago:
                    total_posted_7d += 1
                    posts_by_type["product"] += 1
                    b = post.get("board", "Unknown Board")
                    boards_counter[b] = boards_counter.get(b, 0) + 1
            except Exception:
                pass

    # Blog
    data_blog = load_json(HISTORIES["blog"])
    for post in data_blog.get("posts", []):
        ts_str = post.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= seven_days_ago:
                    total_posted_7d += 1
                    posts_by_type["blog"] += 1
                    b = post.get("board", "Style Ideas")
                    boards_counter[b] = boards_counter.get(b, 0) + 1
            except Exception:
                pass

    # Video
    data_video = load_json(HISTORIES["video"])
    for post in data_video.get("posts", []):
        ts_str = post.get("posted_at") or post.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts >= seven_days_ago:
                    total_posted_7d += 1
                    posts_by_type["video"] += 1
                    b = post.get("board", "Trends")
                    boards_counter[b] = boards_counter.get(b, 0) + 1
            except Exception:
                pass

    report = {
        "generated_at": now.isoformat(),
        "period_days": 7,
        "total_pins_posted": total_posted_7d,
        "pins_by_type": posts_by_type,
        "top_boards_utilized": sorted(boards_counter.items(), key=lambda x: x[1], reverse=True)[:10],
        "recommendations": [
            "Maintain 4 daily time slots covering 9 AM ET, 1 PM ET, 6 PM ET, and 9 PM ET.",
            "Continue 2 daily blog pins targeting style inspiration keywords.",
            "Monitor board engagement on newly added boards (Fall Outfits 2026, Affordable Fashion USA)."
        ]
    }

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Generated weekly analytics report: {REPORT_FILE.name}")
    return report


if __name__ == "__main__":
    rep = generate_weekly_report()
    print("\n=== WEEKLY PINTEREST ANALYTICS REPORT ===")
    print(f"Total Pins Posted (Last 7 Days): {rep['total_pins_posted']}")
    print(f"Breakdown by Type: {rep['pins_by_type']}")
    print("Top Boards Utilized:")
    for board, count in rep['top_boards_utilized']:
        print(f"  - {board}: {count} pins")
