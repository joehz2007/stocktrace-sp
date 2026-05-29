from app.db.connection import connect, init_db


def test_init_db_creates_tables(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    conn = connect(db)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r["name"] for r in rows}
    assert {"stock", "intraday_snapshot", "signal", "notification_log",
            "macro_snapshot", "dividend", "fund_flow", "financial",
            "daily_quote", "daily_indicator", "valuation_forecast"} <= names


def test_connect_returns_row_factory(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    conn = connect(db)
    conn.execute("INSERT INTO stock(code, name, added_at) VALUES('600519','x','2026-01-01')")
    row = conn.execute("SELECT code FROM stock").fetchone()
    assert row["code"] == "600519"
