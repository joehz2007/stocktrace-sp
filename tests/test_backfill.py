import pytest

from app.db.connection import connect, init_db
from app.db.repository import Repository
from app.services.backfill import regen_signals, backfill, synth_daily_snapshot


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    r = Repository(connect(db))
    r.add_stock("600519", "贵州茅台")
    return r


def test_regen_signals_from_intraday_sequence(repo):
    repo.insert_snapshot({"code": "600519", "name": "x", "snapshot_time": "2026-05-28 10:00:00",
                          "ma20": 99.0, "ma60": 100.0, "price": 100.0, "amount_wan": 1.0})
    repo.insert_snapshot({"code": "600519", "name": "x", "snapshot_time": "2026-05-28 10:30:00",
                          "ma20": 101.0, "ma60": 100.0, "price": 100.0, "amount_wan": 1.0})
    n = regen_signals(repo, "2026-05-28")
    types = [s["signal_type"] for s in repo.signals_for("600519", 50)]
    assert "golden_cross" in types
    assert n >= 1


def test_synth_daily_snapshot_shape(repo):
    repo.replace_daily_quotes("600519", [{"trade_date": "2026-05-28", "close": 1700.0,
                                          "open": 1, "high": 1, "low": 1, "volume": 1, "amount": 1}])
    repo.replace_daily_indicators("600519", [{"trade_date": "2026-05-28", "ma20": 1650.0,
                                              "ma60": 1600.0, "vol_ratio_20": 1.0, "trend_status": "多头"}])
    repo.replace_fund_flows("600519", [{"trade_date": "2026-05-28", "main_net_in": 5_000_000.0}])
    snap = synth_daily_snapshot(repo, "600519", "2026-05-28")
    assert snap["snapshot_time"] == "2026-05-28 15:00:00"
    assert snap["ma20"] == 1650.0
    assert snap["dist_ma20_pct"] == pytest.approx((1700 - 1650) / 1650 * 100)
    assert snap["main_net_in"] == pytest.approx(500.0)  # 元 -> 万元


def test_backfill_diffs_consecutive_days(repo):
    repo.insert_fund_flow("600519", "2026-05-27", 0.0)
    repo.insert_fund_flow("600519", "2026-05-28", 0.0)
    repo.replace_daily_quotes("600519", [
        {"trade_date": "2026-05-27", "close": 100.0, "open": 1, "high": 1, "low": 1, "volume": 1, "amount": 1},
        {"trade_date": "2026-05-28", "close": 100.0, "open": 1, "high": 1, "low": 1, "volume": 1, "amount": 1}])
    repo.replace_daily_indicators("600519", [
        {"trade_date": "2026-05-27", "ma20": 99.0, "ma60": 100.0, "vol_ratio_20": 1.0, "trend_status": "x"},
        {"trade_date": "2026-05-28", "ma20": 101.0, "ma60": 100.0, "vol_ratio_20": 1.0, "trend_status": "x"}])
    n = backfill(repo, ["600519"], "2026-05-28", "2026-05-28")
    sigs = repo.signals_for("600519", 50)
    assert any(s["signal_type"] == "golden_cross" and s["snapshot_time"] == "2026-05-28 15:00:00" for s in sigs)
    assert n >= 1
