import pytest

from app.db.connection import connect, init_db
from app.db.repository import Repository
from app.services.snapshot import sync_snapshots


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    r = Repository(connect(db))
    r.add_stock("600519", "贵州茅台")
    r.upsert_financial({"code": "600519", "report_date": "2025-12-31",
                        "net_profit_attr": 8.0e10, "equity_attr": 2.0e11,
                        "total_assets": 3.0e11, "total_liabilities": 1.0e11})
    r.replace_daily_indicators("600519", [{"trade_date": "2026-05-28", "ma20": 1650.0,
                                           "ma60": 1600.0, "vol_ratio_20": 1.0, "trend_status": "多头"}])
    r.replace_fund_flows("600519", [{"trade_date": "2026-05-28", "main_net_in": 5_000_000.0}])
    return r


def test_sync_builds_snapshot_with_metrics(repo):
    quotes = {"600519": {"code": "600519", "name": "贵州茅台", "price": 1700.0, "change_pct": 1.0,
                         "pe_ttm": 30.0, "pb": 8.0, "market_cap_yi": 2000.0, "float_market_cap_yi": 2000.0,
                         "amount_wan": 100000.0, "volume_ratio": 1.2, "turnover_pct": 0.5}}

    def quote_fn(codes):
        return quotes

    def baidu_fn(code):
        return None  # force fallback to local daily fund flow
    snaps = sync_snapshots(repo, ["600519"], quote_fn, baidu_fn, now_fn=lambda: "2026-05-29 10:30:00")
    s = snaps[0]
    assert s["code"] == "600519"
    assert s["ma20"] == 1650.0
    assert s["dist_ma20_pct"] == pytest.approx((1700 - 1650) / 1650 * 100)
    assert s["roe"] is not None
    assert s["debt_to_asset_ratio"] == pytest.approx(1.0e11 / 3.0e11 * 100)
    assert s["main_net_in_source"] == "fund_flow"  # baidu returned None
    assert s["main_net_in"] == pytest.approx(500.0)  # 5,000,000 元 -> 500 万元
    assert len(repo.snapshots_for("600519")) == 1


def test_sync_prefers_baidu_main_net_in(repo):
    quotes = {"600519": {"code": "600519", "name": "贵州茅台", "price": 1700.0, "amount_wan": 100000.0,
                         "market_cap_yi": 2000.0}}
    snaps = sync_snapshots(repo, ["600519"], lambda c: quotes, lambda code: 888.0,
                           now_fn=lambda: "2026-05-29 10:30:00")
    assert snaps[0]["main_net_in"] == 888.0
    assert snaps[0]["main_net_in_source"] == "baidu"
