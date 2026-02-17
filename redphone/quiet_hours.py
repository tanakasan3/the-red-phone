"""Quiet hours management."""

from datetime import datetime, time
from typing import Optional

from dateutil import tz

from .config import config


def parse_time(time_str: str) -> time:
    """Parse time string (HH:MM) to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def is_quiet_hours(check_time: Optional[datetime] = None) -> bool:
    """Check if current time is within quiet hours."""
    if not config.quiet_hours_enabled:
        return False

    # Get timezone
    timezone = tz.gettz(config.timezone) or tz.UTC

    # Get current time in configured timezone
    if check_time is None:
        check_time = datetime.now(timezone)
    elif check_time.tzinfo is None:
        check_time = check_time.replace(tzinfo=tz.UTC).astimezone(timezone)

    current_time = check_time.time()

    # Parse quiet hours
    start = parse_time(config.quiet_hours_start)
    end = parse_time(config.quiet_hours_end)

    # Handle overnight quiet hours (e.g., 22:00 - 08:00)
    if start > end:
        # Quiet hours span midnight
        return current_time >= start or current_time < end
    else:
        # Quiet hours within same day
        return start <= current_time < end


def get_quiet_hours_message() -> str:
    """Get human-readable quiet hours description."""
    if not config.quiet_hours_enabled:
        return "Quiet hours disabled"

    return (
        f"Quiet hours: {config.quiet_hours_start} - {config.quiet_hours_end} "
        f"({config.timezone})"
    )
