import pytest

from app.db.connection import connect, init_db
from app.db.repository import Repository
from app.services.low_freq import refresh_low_freq, LowFreqSources


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    r = Repository(connect(db))
    r.add_stock("600519", "贵州茅台")
    return r


def test_refresh_persists_and_computes_indicators(repo):
    klines = [{"trade_date": f"2026-01-{d:02d}", "open": 100 + d, "high": 100 + d, "low": 100 + d,
               "close": 100.0 + d, "volume": 1000, "amount": 1e8} for d in range(1, 28)]
    src = LowFreqSources(
        dividends_fn=lambda c: [{"report_date": "2025-12-31", "announce_date": "2026-03-01",
                                 "pretax_bonus_per10": 30.0, "plan_or_impl": "实施"}],
        fund_flow_fn=lambda c: [{"trade_date": "2026-05-28", "main_net_in": 1000.0}],
        financial_fn=lambda c: {"report_date": "2025-12-31", "net_profit_attr": 1.0,
                                "equity_attr": 2.0, "total_assets": 3.0, "total_liabilities": 1.0},
        kline_fn=lambda c: klines,
    )
    errors = refresh_low_freq(repo, ["600519"], src)
    assert errors == []
    assert repo.dividends_for("600519")
    assert repo.latest_fund_flow("600519")["main_net_in"] == 1000.0
    assert repo.latest_financial("600519")["report_date"] == "2025-12-31"
    di = repo.latest_daily_indicator("600519")
    assert di["ma20"] is not None  # 27 closes -> MA20 computable, MA60 None


def test_refresh_one_item_failure_does_not_abort(repo):
    captured = []

    def boom(c):
        raise RuntimeError("dividend down")
    src = LowFreqSources(
        dividends_fn=boom,
        fund_flow_fn=lambda c: [{"trade_date": "2026-05-28", "main_net_in": 1.0}],
        financial_fn=lambda c: {"report_date": "2025-12-31", "net_profit_attr": 1.0, "equity_attr": 2.0,
                                "total_assets": 3.0, "total_liabilities": 1.0},
        kline_fn=lambda c: [],
    )
    errors = refresh_low_freq(repo, ["600519"], src,
                              on_error=lambda code, item, exc: captured.append((item, str(exc))))
    assert ("dividends", "dividend down") in captured
    assert repo.latest_fund_flow("600519") is not None  # later items still ran
