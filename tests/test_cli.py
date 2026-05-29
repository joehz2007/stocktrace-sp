import app.cli as cli
from app.db.connection import connect, init_db
from app.db.repository import Repository


def test_cli_init_and_add_and_list(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "t.db")
    monkeypatch.setattr(cli, "DB_PATH", db)
    monkeypatch.setattr("app.wiring.search_fn", lambda kw: [{"code": "600519", "name": "贵州茅台"}])
    cli.main(["init"])
    cli.main(["add", "茅台"])
    cli.main(["list"])
    out = capsys.readouterr().out
    assert "600519" in out
    assert "贵州茅台" in out


def test_cli_sync_uses_injected_sources(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "t.db")
    init_db(db)
    Repository(connect(db)).add_stock("600519", "茅台")
    monkeypatch.setattr(cli, "DB_PATH", db)
    monkeypatch.setattr("app.wiring.quote_fn", lambda codes: {"600519": {"code": "600519", "name": "茅台",
                                                                          "price": 1700.0, "amount_wan": 1.0,
                                                                          "market_cap_yi": 2000.0}})
    monkeypatch.setattr("app.wiring.baidu_fn", lambda code: 100.0)
    monkeypatch.setattr("app.wiring.index_fn", lambda m: {"index_point": 3000.0})
    monkeypatch.setattr("app.wiring.breadth_fn", lambda m: {"up_count": 1, "down_count": 1, "flat_count": 0, "total_count": 2})
    cli.main(["sync"])
    out = capsys.readouterr().out
    assert "600519" in out
