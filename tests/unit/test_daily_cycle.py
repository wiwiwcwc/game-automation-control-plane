from datetime import datetime, timezone

from game_control_plane.domain.daily_cycle import current_period_start


def test_period_before_reset_uses_previous_local_day():
    now = datetime(2026, 8, 24, 3, 59, tzinfo=timezone.utc)
    result = current_period_start(now, "UTC", 240)
    assert result.isoformat() == "2026-08-23T04:00:00+00:00"


def test_period_at_reset_starts_new_day():
    now = datetime(2026, 8, 24, 4, 0, tzinfo=timezone.utc)
    result = current_period_start(now, "UTC", 240)
    assert result.isoformat() == "2026-08-24T04:00:00+00:00"


def test_period_respects_timezone():
    # 03:30 UTC is 11:30 local time, after the 04:00 local reset.
    now = datetime(2026, 8, 24, 3, 30, tzinfo=timezone.utc)
    result = current_period_start(now, "Asia/Shanghai", 240)
    assert result.isoformat() == "2026-08-23T20:00:00+00:00"
