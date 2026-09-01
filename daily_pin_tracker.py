"""
daily_pin_tracker.py — Shared daily pin counter for all Pinterest workflows.

Prevents the combined total of fresh pins + refresh repins + evergreen repins
from exceeding Pinterest's safe organic limit of 15 pins/day, which reduces
the risk of account flagging or shadowbanning.

Usage:
    from daily_pin_tracker import DailyPinTracker

    tracker = DailyPinTracker()
    if not tracker.can_post(n=2):
        logger.info("Daily cap reached — skipping run")
        sys.exit(0)

    # ... post pins ...
    tracker.record(n=2, source="daily_v2")
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
# Pinterest "sweet spot": 8–15 fresh pins/day for established accounts.
# Combined ceiling (fresh + refresh + evergreen) kept at 15 to stay safe.
DAILY_CAP = int(os.getenv("PINTEREST_DAILY_CAP", "15"))

# Weekend cap — Saturdays are high-engagement planning days, allow a small boost
WEEKEND_CAP = int(os.getenv("PINTEREST_WEEKEND_CAP", "18"))

_TRACKER_FILE = Path(__file__).parent / "daily_pin_count.json"


class DailyPinTracker:
    """
    Thread/process-safe daily pin counter backed by a JSON file.

    The file is committed to the repo at the end of each workflow run via
    the existing 'Commit and push history updates' step, so the count
    persists across concurrent GitHub Actions runs on the same day.
    """

    def __init__(self, tracker_file: Optional[Path] = None):
        self._file = tracker_file or _TRACKER_FILE
        self._data = self._load()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _load(self) -> dict:
        today = str(date.today())
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                # Reset if the stored date is not today
                if raw.get("date") == today:
                    return raw
            except Exception as e:
                logger.warning(f"[DailyPinTracker] Could not read {self._file}: {e}")
        return {"date": today, "total": 0, "by_source": {}}

    def _save(self):
        try:
            self._file.write_text(
                json.dumps(self._data, indent=2, default=str), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[DailyPinTracker] Could not write {self._file}: {e}")

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def cap(self) -> int:
        """Return the effective daily cap (higher on weekends)."""
        return WEEKEND_CAP if date.today().weekday() >= 5 else DAILY_CAP

    @property
    def total(self) -> int:
        """Total pins posted today across all sources."""
        return self._data.get("total", 0)

    @property
    def remaining(self) -> int:
        """Pins still allowed today."""
        return max(0, self.cap - self.total)

    def can_post(self, n: int = 1) -> bool:
        """Return True if posting `n` more pins is within today's cap."""
        ok = self.total + n <= self.cap
        if not ok:
            logger.info(
                f"[DailyPinTracker] Daily cap reached: {self.total}/{self.cap} pins "
                f"(tried to add {n}). Skipping."
            )
        return ok

    def record(self, n: int = 1, source: str = "unknown"):
        """Record that `n` pins were posted by `source`."""
        self._data["total"] = self._data.get("total", 0) + n
        by_source = self._data.setdefault("by_source", {})
        by_source[source] = by_source.get(source, 0) + n
        by_source["last_updated"] = datetime.now().isoformat()
        self._save()
        logger.info(
            f"[DailyPinTracker] Recorded {n} pin(s) from '{source}'. "
            f"Total today: {self._data['total']}/{self.cap}"
        )

    def summary(self) -> str:
        by = self._data.get("by_source", {})
        parts = [f"{src}={cnt}" for src, cnt in by.items() if src != "last_updated"]
        return (
            f"Date: {self._data.get('date')} | "
            f"Total: {self.total}/{self.cap} | "
            f"{'  '.join(parts)}"
        )
