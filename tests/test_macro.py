import pytest

from app.db.connection import connect, init_db
from app.db.repository import Repository
from app.services.macro import sync_macro


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    return Repository(connect(db))


def test_sync_macro_writes_both_markets(repo):
    def index_fn(market):
        return {"index_point": 3000.0 if market == "sh" else 10000.0, "change_pct": 1.0}

    def breadth_fn(market):
        return {"up_count": 1000, "down_count": 800, "flat_count": 100, "total_count": 1900}
    sync_macro(repo, index_fn, breadth_fn, now_fn=lambda: "2026-05-29 10:00:00")
    sh = repo.latest_macro("sh")
    assert sh["index_point"] == 3000.0
    assert sh["up_count"] == 1000
    assert repo.latest_macro("sz")["index_point"] == 10000.0
