import app.wiring as wiring
from app.db.connection import connect, init_db
from app.db.repository import Repository
from app.web import create_app


def _client(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    Repository(connect(db)).add_stock("600519", "贵州茅台")
    app = create_app(db)
    app.config["TESTING"] = True
    return app.test_client(), db


def test_index_renders(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "贵州茅台".encode() in resp.data or b"600519" in resp.data


def test_signals_page(tmp_path):
    client, _ = _client(tmp_path)
    resp = client.get("/signals")
    assert resp.status_code == 200
    assert "阈值".encode() in resp.data


def test_add_route(tmp_path, monkeypatch):
    client, db = _client(tmp_path)
    monkeypatch.setattr(wiring, "search_fn", lambda kw: [{"code": "000858", "name": "五粮液"}])
    resp = client.post("/add", data={"text": "五粮液"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"000858" in resp.data


def test_sync_route(tmp_path, monkeypatch):
    client, db = _client(tmp_path)
    monkeypatch.setattr(wiring, "quote_fn", lambda codes: {"600519": {"code": "600519", "name": "茅台",
                                                                       "price": 1700.0, "amount_wan": 1.0,
                                                                       "market_cap_yi": 2000.0}})
    monkeypatch.setattr(wiring, "baidu_fn", lambda code: 1.0)
    monkeypatch.setattr(wiring, "index_fn", lambda m: {"index_point": 3000.0})
    monkeypatch.setattr(wiring, "breadth_fn", lambda m: {"up_count": 1, "down_count": 1, "flat_count": 0, "total_count": 2})
    resp = client.get("/sync", follow_redirects=True)
    assert resp.status_code == 200
