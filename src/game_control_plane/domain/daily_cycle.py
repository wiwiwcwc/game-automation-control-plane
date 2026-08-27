from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value


def current_period_start(
    now: datetime,
    timezone_id: str,
    reset_minute: int,
) -> datetime:
    """Return the UTC instant at which the current daily period began.

    Reset minutes are measured from local midnight. The returned value is
    timezone-aware UTC and is suitable for use as the durable completion key.
    """

    _require_aware(now)
    if not 0 <= reset_minute <= 1439:
        raise ValueError("reset_minute must be between 0 and 1439")
    zone = ZoneInfo(timezone_id)
    local_now = now.astimezone(zone)
    local_date = local_now.date()
    reset = _reset_for_date(local_date, zone, reset_minute)
    if local_now < reset:
        reset = _reset_for_date(local_date - timedelta(days=1), zone, reset_minute)
    return reset.astimezone(UTC)


def _reset_for_date(day: date, zone: ZoneInfo, reset_minute: int) -> datetime:
    hours, minutes = divmod(reset_minute, 60)
    return datetime.combine(day, time(hours, minutes), tzinfo=zone)


def period_start_iso(now: datetime, timezone_id: str, reset_minute: int) -> str:
    return current_period_start(now, timezone_id, reset_minute).isoformat()
