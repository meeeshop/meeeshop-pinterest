"""
seasonal_calendar.py — USA Women's Fashion Pinterest Seasonal Calendar Engine
Determines current and upcoming seasonal shopping peaks, events, and keyword prompts.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List

EVENT_SCHEDULE = [
    {"name": "New Year & Winter Clearance", "start_month": 1, "start_day": 1, "end_month": 1, "end_day": 20, "badge": "❄️ WINTER STYLE"},
    {"name": "Valentine's Day & Date Night", "start_month": 1, "start_day": 21, "end_month": 2, "end_day": 14, "badge": "💘 DATE NIGHT"},
    {"name": "Spring Break & Resort Wear", "start_month": 2, "start_day": 15, "end_month": 3, "end_day": 31, "badge": "🌴 RESORT WEAR"},
    {"name": "Easter & Spring Outfits", "start_month": 4, "start_day": 1, "end_month": 4, "end_day": 25, "badge": "🌸 SPRING STYLE"},
    {"name": "Mother's Day & Graduation", "start_month": 4, "start_day": 26, "end_month": 5, "end_day": 20, "badge": "💐 BRUNCH STYLE"},
    {"name": "Summer Kickoff & Wedding Guest", "start_month": 5, "start_day": 21, "end_month": 6, "end_day": 25, "badge": "☀️ SUMMER LOOK"},
    {"name": "4th of July & Summer Vacation", "start_month": 6, "start_day": 26, "end_month": 7, "end_day": 15, "badge": "🇺🇸 SUMMER VACAY"},
    {"name": "Back to School & Late Summer", "start_month": 7, "start_day": 16, "end_month": 8, "end_day": 25, "badge": "✏️ BACK TO SCHOOL"},
    {"name": "Labor Day & Fall Transition", "start_month": 8, "start_day": 26, "end_month": 9, "end_day": 15, "badge": "🍂 FALL PREVIEW"},
    {"name": "Cozy Fall & Pumpkin Patch", "start_month": 9, "start_day": 16, "end_month": 10, "end_day": 31, "badge": "🍁 COZY FALL"},
    {"name": "Thanksgiving & Friendsgiving", "start_month": 11, "start_day": 1, "end_month": 11, "end_day": 26, "badge": "🦃 THANKSGIVING"},
    {"name": "Holiday Parties & NYE", "start_month": 11, "start_day": 27, "end_month": 12, "end_day": 31, "badge": "✨ HOLIDAY GLAM"}
]


def get_current_seasonal_event(target_date: datetime = None) -> Dict[str, Any]:
    """
    Returns the active seasonal shopping event for USA women on Pinterest based on date.
    """
    if not target_date:
        target_date = datetime.now()

    month = target_date.month
    day = target_date.day

    for event in EVENT_SCHEDULE:
        s_m, s_d = event["start_month"], event["start_day"]
        e_m, e_d = event["end_month"], event["end_day"]

        if (s_m == e_m and month == s_m and s_d <= day <= e_d) or \
           (s_m < e_m and ((month == s_m and day >= s_d) or (month == e_m and day <= e_d))):
            return event

    return EVENT_SCHEDULE[6]  # Fallback to Summer Vacation


def is_event_within_days(days: int = 14) -> List[Dict[str, Any]]:
    """
    Checks if a major shopping event starts within the next N days.
    """
    now = datetime.now()
    future = now + timedelta(days=days)
    upcoming = []

    for event in EVENT_SCHEDULE:
        s_m, s_d = event["start_month"], event["start_day"]
        if now.month <= s_m <= future.month:
            upcoming.append(event)

    return upcoming


if __name__ == "__main__":
    event = get_current_seasonal_event()
    print(f"Active Seasonal Event: {event['name']} (Badge: {event['badge']})")
