"""
Timezone-aware scheduling for Pinterest pin posting.
Posts pins at optimal times across US timezones to maximize reach.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# US timezone to UTC offset mapping (EST example: -5)
TIMEZONE_OFFSETS = {
    "EST": -5,  # Eastern Standard Time
    "CST": -6,  # Central Standard Time
    "MST": -7,  # Mountain Standard Time
    "PST": -8,  # Pacific Standard Time
}

# Peak shopping hours for women by timezone
PEAK_HOURS = {
    "EST": [9, 13, 19, 21],  # 9 AM, 1 PM, 7 PM, 9 PM EST
    "CST": [9, 13, 19, 21],  # 9 AM, 1 PM, 7 PM, 9 PM CST
    "MST": [9, 13, 19, 21],  # 9 AM, 1 PM, 7 PM, 9 PM MST
    "PST": [9, 13, 19, 21],  # 9 AM, 1 PM, 7 PM, 9 PM PST
}


def get_peak_hours_utc() -> Dict[str, List[int]]:
    """
    Convert peak shopping hours to UTC equivalents.

    Returns:
        Dict mapping timezone to list of UTC hours for peak posting
    """
    peak_utc = {}

    for tz, offset in TIMEZONE_OFFSETS.items():
        peak_hours = PEAK_HOURS[tz]
        # Convert local hours to UTC: UTC = Local + offset
        utc_hours = [
            (hour - offset) % 24 for hour in peak_hours
        ]
        peak_utc[tz] = sorted(set(utc_hours))

    return peak_utc


def should_post_now(board_timezone: Optional[str] = None) -> bool:
    """
    Check if current UTC time matches a peak hour for the board's timezone.

    Args:
        board_timezone: Timezone the board targets (EST, CST, MST, PST)

    Returns:
        True if current time is peak hour, False otherwise
    """
    if not board_timezone:
        return True  # Post immediately if no timezone specified

    peak_utc = get_peak_hours_utc()
    if board_timezone not in peak_utc:
        logger.warning(f"Unknown timezone: {board_timezone}")
        return True  # Post if timezone unknown

    current_utc_hour = datetime.utcnow().hour
    peak_hours = peak_utc[board_timezone]

    is_peak = current_utc_hour in peak_hours
    logger.info(
        f"Board timezone {board_timezone}: peak hours UTC{peak_hours}, "
        f"current UTC{current_utc_hour}: {'✓ posting' if is_peak else '✗ skipping'}"
    )

    return is_peak


def get_next_peak_time(board_timezone: str) -> datetime:
    """
    Get the next peak posting time for a board's timezone.

    Args:
        board_timezone: Timezone the board targets

    Returns:
        datetime of next peak posting hour
    """
    peak_utc = get_peak_hours_utc()
    if board_timezone not in peak_utc:
        return datetime.utcnow()  # Now if unknown

    peak_hours = peak_utc[board_timezone]
    now = datetime.utcnow()
    current_hour = now.hour

    # Find next peak hour today
    for hour in peak_hours:
        if hour > current_hour:
            next_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            return next_time

    # If no more peak hours today, use first peak hour tomorrow
    tomorrow = now + timedelta(days=1)
    first_peak = peak_hours[0]
    return tomorrow.replace(hour=first_peak, minute=0, second=0, microsecond=0)


def load_board_timezones(config_path: Path = None) -> Dict[str, str]:
    """
    Load board-to-timezone mapping from JSON config.

    Args:
        config_path: Path to JSON file with board timezone mapping

    Returns:
        Dict mapping board name to timezone (EST/CST/MST/PST)
    """
    if not config_path:
        config_path = Path(__file__).parent / "board_timezones.json"

    if not config_path.exists():
        logger.warning(f"Board timezone config not found: {config_path}")
        return {}

    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load board timezones: {e}")
        return {}


def create_scheduling_report(boards: List[Dict]) -> str:
    """
    Generate a report of optimal posting times for all boards.

    Args:
        boards: List of board dicts with 'name' and optional 'timezone' keys

    Returns:
        Formatted string report of posting schedule
    """
    report = ["=" * 70]
    report.append("PINTEREST PIN POSTING SCHEDULE (24-hour cycle)")
    report.append("=" * 70)
    report.append(f"Generated: {datetime.utcnow().isoformat()}\n")

    peak_utc = get_peak_hours_utc()

    for tz, utc_hours in peak_utc.items():
        report.append(f"\n{tz} Timezone:")
        report.append(f"  Peak posting hours (UTC): {utc_hours}")

        # Convert back to local time for readability
        offset = TIMEZONE_OFFSETS[tz]
        local_hours = [(h + offset) % 24 for h in utc_hours]
        report.append(f"  Peak posting hours ({tz}): {sorted(local_hours)}")

    report.append("\n" + "=" * 70)
    report.append(f"Boards configured: {len(boards)}")
    for board in boards:
        board_tz = board.get("timezone", "N/A")
        report.append(f"  - {board['name']}: {board_tz}")

    return "\n".join(report)
