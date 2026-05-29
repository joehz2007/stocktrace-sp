import pytest

from app.services import metrics


def test_dividend_yield_ttm():
    dividends = [
        {"report_date": "2025-12-31", "announce_date": "2026-03-01", "pretax_bonus_per10": 30.0},
        {"report_date": "2025-12-31", "announce_date": "2026-02-01", "pretax_bonus_per10": 25.0},  # superseded
    ]
    y = metrics.dividend_yield_ttm(dividends, total_shares=1.256e9, market_cap=2.0e12)
    assert y == pytest.approx(3.0 * 1.256e9 / 2.0e12 * 100, rel=1e-6)


def test_dividend_yield_none_when_no_market_cap():
    assert metrics.dividend_yield_ttm([], total_shares=1.0, market_cap=0) is None


def test_roe_annualization_q1():
    assert metrics.roe(net_profit_attr=100, equity_attr=1000, report_month=3) == pytest.approx(40.0)


def test_roe_annualization_q3():
    assert metrics.roe(100, 1000, 9) == pytest.approx(100 * (4 / 3) / 1000 * 100)


def test_roe_full_year():
    assert metrics.roe(100, 1000, 12) == pytest.approx(10.0)


def test_roe_none_when_zero_equity():
    assert metrics.roe(100, 0, 12) is None


def test_debt_to_asset_ratio():
    assert metrics.debt_to_asset_ratio(300, 1000) == pytest.approx(30.0)
    assert metrics.debt_to_asset_ratio(300, 0) is None


def test_dynamic_pe_prefers_eps():
    pe, src = metrics.dynamic_pe(price=100, forecast_eps=5.0, market_cap_yi=None, forecast_net_profit_yi=None)
    assert pe == pytest.approx(20.0) and src == "eps"


def test_dynamic_pe_falls_back_to_net_profit():
    pe, src = metrics.dynamic_pe(price=100, forecast_eps=None, market_cap_yi=200.0, forecast_net_profit_yi=10.0)
    assert pe == pytest.approx(20.0) and src == "net_profit"


def test_dynamic_pe_none():
    assert metrics.dynamic_pe(100, None, None, None) == (None, None)


def test_ma_distance_pct():
    assert metrics.distance_pct(price=110, ma=100) == pytest.approx(10.0)
    assert metrics.distance_pct(110, None) is None
    assert metrics.distance_pct(110, 0) is None


def test_trend_status():
    assert metrics.trend_status(price=110, ma20=105, ma60=100) == "多头：价高于MA20，MA20高于MA60"
    assert metrics.trend_status(90, 95, 100) == "空头：价低于MA20，MA20低于MA60"
    assert metrics.trend_status(110, 95, 100) == "中性偏强：价高于MA60"
    # price<MA60 but not full bearish alignment (price>MA20) -> 中性偏弱
    assert metrics.trend_status(95, 90, 100) == "中性偏弱：价低于MA60"
    assert metrics.trend_status(110, 105, None) is None


def test_moving_average():
    closes = list(range(1, 21))  # 1..20
    assert metrics.moving_average(closes, 20) == pytest.approx(10.5)
    assert metrics.moving_average(closes, 60) is None  # not enough data
