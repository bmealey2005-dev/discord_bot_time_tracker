from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class WeekWindow:
    start_ts: int  # unix seconds
    end_ts: int    # unix seconds (exclusive)
    tz_name: str
    week_start: int  # 0=Mon..6=Sun


def get_zoneinfo(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        # Fall back instead of crashing the bot due to a misconfig.
        return ZoneInfo("UTC")


def compute_week_window(
    *,
    now: datetime,
    tz_name: str,
    week_start: int,
    week_offset: int = 0,
) -> WeekWindow:
    """
    Returns the [start,end) unix-second window for the given week in tz_name.

    week_start: 0=Mon..6=Sun
    week_offset: 0=current week, -1=previous, +1=next, ...
    """
    if week_start < 0 or week_start > 6:
        raise ValueError("week_start must be between 0 and 6.")

    tz = get_zoneinfo(tz_name)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    local_now = now.astimezone(tz)
    local_date = local_now.date()

    # Compute week start date in local time.
    delta_days = (local_now.weekday() - week_start) % 7
    start_date = local_date - timedelta(days=delta_days) + timedelta(days=week_offset * 7)
    start_local = datetime.combine(start_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=7)

    return WeekWindow(
        start_ts=int(start_local.timestamp()),
        end_ts=int(end_local.timestamp()),
        tz_name=tz_name,
        week_start=week_start,
    )


def overlap_seconds(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    start = max(int(a_start), int(b_start))
    end = min(int(a_end), int(b_end))
    return max(0, end - start)

