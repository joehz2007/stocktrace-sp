from datetime import datetime

from app.scheduler import should_run_intraday


def test_intraday_window_weekday_morning():
    assert should_run_intraday(datetime(2026, 5, 29, 10, 0))   # Friday 10:00
    assert should_run_intraday(datetime(2026, 5, 29, 9, 30))
    assert should_run_intraday(datetime(2026, 5, 29, 11, 35))
    assert not should_run_intraday(datetime(2026, 5, 29, 11, 36))


def test_intraday_window_afternoon():
    assert should_run_intraday(datetime(2026, 5, 29, 13, 0))
    assert should_run_intraday(datetime(2026, 5, 29, 15, 10))
    assert not should_run_intraday(datetime(2026, 5, 29, 12, 0))


def test_intraday_skips_weekend():
    assert not should_run_intraday(datetime(2026, 5, 30, 10, 0))  # Saturday
