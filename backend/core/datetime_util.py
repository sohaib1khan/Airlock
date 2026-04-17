"""Helpers for datetime comparisons when SQLite returns naive values."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def to_utc_aware(dt: datetime) -> datetime:
    """Normalize ORM datetimes so comparisons with datetime.now(timezone.utc) never mix naive/aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_rfc3339_utc(dt: datetime) -> str:
    """RFC 3339 instant in UTC with ``Z`` suffix so browsers parse a single absolute time (not naive local)."""
    a = to_utc_aware(dt)
    iso = a.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    return iso


def format_datetime_for_display(dt: datetime | None, tz_name: str) -> str | None:
    """Format a UTC instant for humans in the given IANA timezone (e.g. ``America/New_York``)."""
    if dt is None:
        return None
    a = to_utc_aware(dt)
    name = (tz_name or "").strip() or "UTC"
    try:
        zi = ZoneInfo(name)
    except Exception:
        zi = ZoneInfo("UTC")
    local = a.astimezone(zi)
    return local.strftime("%Y-%m-%d %I:%M:%S %p %Z")
