"""
Time window schema and resolution utilities.

A TimeWindow describes the user's selection for the analysis period.
resolve_time_window() converts it into four concrete UTC datetimes:
  c_start, c_end   — current period
  p_start, p_end   — previous period (automatic baseline)

get_ingest_since() returns the earliest datetime to fetch when ingesting
data — always equal to p_start for preset/custom, or 3 years back for
full_history (project_start is unknown at ingest time).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel


class TimeWindow(BaseModel):
    mode: str  # "preset" | "full_history" | "custom"
    preset: Optional[str] = None  # "7d" | "30d" | "90d" | "6m"
    custom_start: Optional[datetime] = None
    custom_end: Optional[datetime] = None


_PRESET_DAYS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6m": 182,
}

DEFAULT_PRESET = "30d"


def resolve_time_window(
    window: TimeWindow,
    project_start: Optional[datetime] = None,
) -> tuple[datetime, datetime, datetime, datetime]:
    """
    Return (c_start, c_end, p_start, p_end) in UTC.

    project_start — earliest known event timestamp; used for edge-case handling.
    """
    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Preset
    # ------------------------------------------------------------------
    if window.mode == "preset" or window.mode not in ("full_history", "custom"):
        preset = window.preset or DEFAULT_PRESET
        delta_days = _PRESET_DAYS.get(preset, 30)
        delta = timedelta(days=delta_days)

        c_end = now
        c_start = now - delta
        p_end = c_start
        p_start = c_start - delta

        # Edge case: project too young for the selected window
        if project_start is not None and p_start < project_start:
            available = now - project_start
            if available < delta:
                # Split available history in half
                half = available / 2
                midpoint = project_start + half
                return midpoint, now, project_start, midpoint
            else:
                p_start = project_start

        return c_start, c_end, p_start, p_end

    # ------------------------------------------------------------------
    # Full history
    # ------------------------------------------------------------------
    if window.mode == "full_history":
        if project_start is None:
            # Fall back to 90-day window
            project_start = now - timedelta(days=90)
        available = now - project_start
        midpoint = project_start + available / 2
        return midpoint, now, project_start, midpoint

    # ------------------------------------------------------------------
    # Custom range
    # ------------------------------------------------------------------
    if window.mode == "custom":
        c_start = window.custom_start or (now - timedelta(days=30))
        c_end = window.custom_end or now
        # Ensure both are timezone-aware
        if c_start.tzinfo is None:
            c_start = c_start.replace(tzinfo=timezone.utc)
        if c_end.tzinfo is None:
            c_end = c_end.replace(tzinfo=timezone.utc)
        duration = c_end - c_start
        p_end = c_start
        p_start = c_start - duration
        if project_start is not None and p_start < project_start:
            p_start = project_start
        return c_start, c_end, p_start, p_end

    # Fallback — should not reach here
    delta = timedelta(days=30)
    c_end = now
    c_start = now - delta
    return c_start, c_end, c_start - delta, c_start


def get_ingest_since(window: TimeWindow) -> datetime:
    """
    Return the earliest datetime to pass as `since` when fetching raw events
    from a Git adapter.  This covers both the current AND previous period in
    a single fetch.
    """
    now = datetime.now(timezone.utc)

    if window.mode == "preset" or window.mode not in ("full_history", "custom"):
        preset = window.preset or DEFAULT_PRESET
        delta_days = _PRESET_DAYS.get(preset, 30)
        # Go back 2× the window to cover both periods
        return now - timedelta(days=delta_days * 2)

    if window.mode == "full_history":
        # Fetch maximum history (3 years); project_start is unknown at this point
        return now - timedelta(days=365 * 3)

    if window.mode == "custom":
        if window.custom_start:
            c_start = window.custom_start
            if c_start.tzinfo is None:
                c_start = c_start.replace(tzinfo=timezone.utc)
            c_end = window.custom_end or now
            if c_end.tzinfo is None:
                c_end = c_end.replace(tzinfo=timezone.utc)
            duration = c_end - c_start
            return c_start - duration  # p_start
        return now - timedelta(days=60)

    return now - timedelta(days=60)
