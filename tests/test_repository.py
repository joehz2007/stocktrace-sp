import pytest

from app.db.connection import connect, init_db
from app.db.repository import Repository


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    return Repository(connect(db))


def test_add_and_list_stocks(repo):
    repo.add_stock("600519", "贵州茅台")
    repo.add_stock("600519", "贵州茅台")  # idempotent upsert
    repo.add_stock("000858", "五粮液")
    stocks = repo.list_stocks()
    assert {s["code"] for s in stocks} == {"600519", "000858"}


def test_insert_and_latest_snapshot(repo):
    repo.add_stock("600519", "贵州茅台")
    repo.insert_snapshot({"code": "600519", "name": "贵州茅台", "snapshot_time": "2026-05-29 10:00:00", "price": 1700.0})
    repo.insert_snapshot({"code": "600519", "name": "贵州茅台", "snapshot_time": "2026-05-29 10:30:00", "price": 1710.0})
    latest = repo.latest_snapshot_per_stock()
    assert latest[0]["price"] == 1710.0
    recent = repo.snapshots_for("600519", limit=10)
    assert len(recent) == 2
    assert recent[0]["snapshot_time"] == "2026-05-29 10:30:00"  # desc


def test_signals_dedup_query(repo):
    sid = repo.insert_signal({"code": "600519", "name": "x", "signal_type": "golden_cross",
                              "level": "high", "snapshot_time": "2026-05-29 10:00:00", "detail": "d"})
    assert isinstance(sid, int)
    repo.log_notification(sid, "a@x.com", "success", None)
    notified = repo.notified_signal_recipient_pairs()
    assert (sid, "a@x.com") in notified


def test_fund_flow_latest(repo):
    repo.insert_fund_flow("600519", "2026-05-27", 1000.0)
    repo.insert_fund_flow("600519", "2026-05-28", 2000.0)
    assert repo.latest_fund_flow("600519")["main_net_in"] == 2000.0
