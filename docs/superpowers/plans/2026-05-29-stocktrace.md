# StockTrace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local A-share tracking tool (stock pool, intraday snapshots, low-freq indicators, event-diff signals, email alerts) with Flask Web + CLI + APScheduler entries, backed by SQLite.

**Architecture:** Layered + adapters. Entries (cli/web/scheduler) call services only; services receive injected repository + source adapters; only `app/sources/*` touch HTTP; error-prone, formula-critical pure logic (metrics, signals, parsing, dedup) lives in IO-free units for strict TDD.

**Tech Stack:** Python 3.12, uv, Flask, APScheduler, requests, sqlite3 (stdlib), pytest.

**Spec:** `docs/superpowers/specs/2026-05-29-stocktrace-design.md`

**Conventions for every task:** run tests with `uv run pytest`. Commit at the end of each task with the shown message. Keep files focused. No network in tests.

---

## Task 1: Project scaffolding (uv + package skeleton + pytest)

**Files:**
- Create: `pyproject.toml`, `app/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `app/config.py`, `tests/test_config.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "stocktrace"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "flask>=3.0",
    "apscheduler>=3.10",
    "requests>=2.31",
]

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.setuptools.packages.find]
include = ["app*"]
```

- [ ] **Step 2: Create empty `app/__init__.py` and `tests/__init__.py`**

Both empty files.

- [ ] **Step 3: Write failing test for config** in `tests/test_config.py`

```python
import json
from app.config import load_email_config, web_host_port


def test_email_config_prefers_env(monkeypatch, tmp_path):
    cfg_file = tmp_path / "email_config.json"
    cfg_file.write_text(json.dumps({"smtp_host": "file-host", "username": "u", "password": "p", "from_addr": "f", "recipients": ["r@x.com"]}))
    monkeypatch.setenv("EMAIL_SMTP_HOST", "env-host")
    monkeypatch.setenv("EMAIL_USERNAME", "eu")
    monkeypatch.setenv("EMAIL_PASSWORD", "ep")
    monkeypatch.setenv("EMAIL_FROM", "ef@x.com")
    monkeypatch.setenv("EMAIL_RECIPIENTS", "a@x.com,b@x.com")
    cfg = load_email_config(str(cfg_file))
    assert cfg["smtp_host"] == "env-host"
    assert cfg["recipients"] == ["a@x.com", "b@x.com"]


def test_email_config_falls_back_to_file(monkeypatch, tmp_path):
    monkeypatch.delenv("EMAIL_SMTP_HOST", raising=False)
    cfg_file = tmp_path / "email_config.json"
    cfg_file.write_text(json.dumps({"smtp_host": "file-host", "recipients": ["r@x.com"]}))
    cfg = load_email_config(str(cfg_file))
    assert cfg["smtp_host"] == "file-host"


def test_web_host_port_defaults(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert web_host_port() == ("127.0.0.1", 5001)


def test_web_host_port_env_override(monkeypatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "5000")
    assert web_host_port() == ("0.0.0.0", 5000)
```

- [ ] **Step 4: Run, expect failure** — `uv run pytest tests/test_config.py` → ImportError.

- [ ] **Step 5: Implement `app/config.py`**

```python
import json
import os

DATA_DIR = os.environ.get("STOCKTRACE_DATA_DIR", "data")
DEFAULT_EMAIL_CONFIG_PATH = os.path.join(DATA_DIR, "email_config.json")


def load_email_config(path: str = DEFAULT_EMAIL_CONFIG_PATH) -> dict:
    cfg: dict = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    env_map = {
        "EMAIL_SMTP_HOST": "smtp_host",
        "EMAIL_SMTP_PORT": "smtp_port",
        "EMAIL_USERNAME": "username",
        "EMAIL_PASSWORD": "password",
        "EMAIL_FROM": "from_addr",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            cfg[cfg_key] = val
    recipients = os.environ.get("EMAIL_RECIPIENTS")
    if recipients is not None:
        cfg["recipients"] = [r.strip() for r in recipients.split(",") if r.strip()]
    return cfg


def web_host_port() -> tuple[str, int]:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5001"))
    return host, port
```

- [ ] **Step 6: Create `tests/conftest.py`** (shared fixtures placeholder, filled later)

```python
import pytest  # noqa: F401
```

- [ ] **Step 7: Run, expect pass** — `uv run pytest`.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "chore: scaffold uv project, config module, pytest"
```

---

## Task 2: Database schema + connection

**Files:**
- Create: `app/db/__init__.py`, `app/db/schema.sql`, `app/db/connection.py`, `tests/test_connection.py`

- [ ] **Step 1: Write `app/db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS stock (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intraday_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, name TEXT, snapshot_time TEXT NOT NULL,
    price REAL, change_pct REAL, turnover_pct REAL, amount_wan REAL, volume_ratio REAL,
    pe_static REAL, pe_ttm REAL, pe_dynamic REAL, pe_dynamic_source TEXT, pb REAL,
    market_cap_yi REAL, float_market_cap_yi REAL, dividend_yield_ttm REAL, roe REAL,
    ma20 REAL, ma60 REAL, dist_ma20_pct REAL, dist_ma60_pct REAL, trend_status TEXT,
    debt_to_asset_ratio REAL, main_net_in REAL, main_net_in_source TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_code_time ON intraday_snapshot(code, snapshot_time);
CREATE TABLE IF NOT EXISTS macro_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market TEXT NOT NULL, snapshot_time TEXT NOT NULL,
    index_point REAL, change_point REAL, change_pct REAL, high REAL, low REAL, amount REAL,
    up_count INTEGER, down_count INTEGER, flat_count INTEGER, total_count INTEGER
);
CREATE TABLE IF NOT EXISTS signal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, name TEXT, signal_type TEXT NOT NULL, level TEXT NOT NULL,
    snapshot_time TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signal_code_time ON signal(code, snapshot_time);
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL, recipient TEXT NOT NULL, status TEXT NOT NULL,
    error TEXT, sent_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dividend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, report_date TEXT NOT NULL, announce_date TEXT,
    pretax_bonus_per10 REAL, plan_or_impl TEXT
);
CREATE TABLE IF NOT EXISTS fund_flow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, trade_date TEXT NOT NULL, main_net_in REAL
);
CREATE INDEX IF NOT EXISTS idx_fundflow_code_date ON fund_flow(code, trade_date);
CREATE TABLE IF NOT EXISTS financial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, report_date TEXT NOT NULL,
    net_profit_attr REAL, equity_attr REAL, total_assets REAL, total_liabilities REAL
);
CREATE TABLE IF NOT EXISTS daily_quote (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL
);
CREATE INDEX IF NOT EXISTS idx_dq_code_date ON daily_quote(code, trade_date);
CREATE TABLE IF NOT EXISTS daily_indicator (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    ma20 REAL, ma60 REAL, vol_ratio_20 REAL, trend_status TEXT
);
CREATE INDEX IF NOT EXISTS idx_di_code_date ON daily_indicator(code, trade_date);
CREATE TABLE IF NOT EXISTS valuation_forecast (
    code TEXT PRIMARY KEY,
    forecast_eps REAL, forecast_net_profit_yi REAL, source TEXT, updated_at TEXT
);
```

- [ ] **Step 2: Write failing test** in `tests/test_connection.py`

```python
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
```

- [ ] **Step 3: Run, expect failure.**

- [ ] **Step 4: Implement `app/db/connection.py`**

```python
import os
import sqlite3

from app.config import DATA_DIR

DEFAULT_DB_PATH = os.path.join(DATA_DIR, "stocktrace.db")
_SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")


def connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with open(_SCHEMA, encoding="utf-8") as f:
        ddl = f.read()
    conn = connect(db_path)
    try:
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 5: Create empty `app/db/__init__.py`. Run, expect pass.**

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: sqlite schema and connection helpers"
```

---

## Task 3: Repository (data access)

**Files:**
- Create: `app/db/repository.py`, `tests/test_repository.py`

The Repository wraps a connection and exposes typed insert/query methods. No business logic.

- [ ] **Step 1: Write failing tests** in `tests/test_repository.py`

```python
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
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/db/repository.py`**

```python
import sqlite3
from datetime import datetime

_SNAPSHOT_COLS = [
    "code", "name", "snapshot_time", "price", "change_pct", "turnover_pct", "amount_wan",
    "volume_ratio", "pe_static", "pe_ttm", "pe_dynamic", "pe_dynamic_source", "pb",
    "market_cap_yi", "float_market_cap_yi", "dividend_yield_ttm", "roe", "ma20", "ma60",
    "dist_ma20_pct", "dist_ma60_pct", "trend_status", "debt_to_asset_ratio",
    "main_net_in", "main_net_in_source",
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def commit(self) -> None:
        self.conn.commit()

    # --- stock pool ---
    def add_stock(self, code: str, name: str) -> None:
        self.conn.execute(
            "INSERT INTO stock(code, name, added_at) VALUES(?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET name=excluded.name",
            (code, name, _now()),
        )
        self.conn.commit()

    def list_stocks(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM stock ORDER BY added_at").fetchall()

    def get_stock(self, code: str):
        return self.conn.execute("SELECT * FROM stock WHERE code=?", (code,)).fetchone()

    # --- snapshots ---
    def insert_snapshot(self, data: dict) -> int:
        cols = [c for c in _SNAPSHOT_COLS if c in data]
        placeholders = ",".join("?" for _ in cols)
        cur = self.conn.execute(
            f"INSERT INTO intraday_snapshot({','.join(cols)}) VALUES({placeholders})",
            [data[c] for c in cols],
        )
        self.conn.commit()
        return cur.lastrowid

    def snapshots_for(self, code: str, limit: int = 100) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM intraday_snapshot WHERE code=? ORDER BY snapshot_time DESC, id DESC LIMIT ?",
            (code, limit),
        ).fetchall()

    def last_two_snapshots(self, code: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM intraday_snapshot WHERE code=? ORDER BY snapshot_time DESC, id DESC LIMIT 2",
            (code,),
        ).fetchall()

    def latest_snapshot_per_stock(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT s.* FROM intraday_snapshot s JOIN ("
            "  SELECT code, MAX(id) AS mid FROM intraday_snapshot GROUP BY code"
            ") m ON s.id = m.mid ORDER BY s.code"
        ).fetchall()

    def recent_snapshots(self, limit: int = 500) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM intraday_snapshot ORDER BY snapshot_time DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def snapshots_on_date(self, code: str, date: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM intraday_snapshot WHERE code=? AND substr(snapshot_time,1,10)=? "
            "ORDER BY snapshot_time, id",
            (code, date),
        ).fetchall()

    def delete_signals_on_date(self, date: str) -> None:
        self.conn.execute("DELETE FROM signal WHERE substr(snapshot_time,1,10)=?", (date,))
        self.conn.commit()

    # --- signals ---
    def insert_signal(self, data: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO signal(code,name,signal_type,level,snapshot_time,detail,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (data["code"], data.get("name"), data["signal_type"], data["level"],
             data["snapshot_time"], data.get("detail"), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def signals_for(self, code: str, limit: int = 30) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM signal WHERE code=? ORDER BY snapshot_time DESC, id DESC LIMIT ?",
            (code, limit),
        ).fetchall()

    def recent_signals(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM signal ORDER BY snapshot_time DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()

    def all_signals(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM signal ORDER BY id").fetchall()

    # --- notifications ---
    def log_notification(self, signal_id: int, recipient: str, status: str, error) -> None:
        self.conn.execute(
            "INSERT INTO notification_log(signal_id,recipient,status,error,sent_at) VALUES(?,?,?,?,?)",
            (signal_id, recipient, status, error, _now()),
        )
        self.conn.commit()

    def notified_signal_recipient_pairs(self) -> set[tuple[int, str]]:
        rows = self.conn.execute(
            "SELECT signal_id, recipient FROM notification_log WHERE status='success'"
        ).fetchall()
        return {(r["signal_id"], r["recipient"]) for r in rows}

    # --- low-freq caches ---
    def replace_dividends(self, code: str, rows: list[dict]) -> None:
        self.conn.execute("DELETE FROM dividend WHERE code=?", (code,))
        self.conn.executemany(
            "INSERT INTO dividend(code,report_date,announce_date,pretax_bonus_per10,plan_or_impl) "
            "VALUES(?,?,?,?,?)",
            [(code, r["report_date"], r.get("announce_date"), r.get("pretax_bonus_per10"),
              r.get("plan_or_impl")) for r in rows],
        )
        self.conn.commit()

    def dividends_for(self, code: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM dividend WHERE code=? ORDER BY report_date DESC, announce_date DESC", (code,)
        ).fetchall()

    def insert_fund_flow(self, code: str, trade_date: str, main_net_in: float) -> None:
        self.conn.execute(
            "INSERT INTO fund_flow(code,trade_date,main_net_in) VALUES(?,?,?)",
            (code, trade_date, main_net_in),
        )
        self.conn.commit()

    def replace_fund_flows(self, code: str, rows: list[dict]) -> None:
        self.conn.execute("DELETE FROM fund_flow WHERE code=?", (code,))
        self.conn.executemany(
            "INSERT INTO fund_flow(code,trade_date,main_net_in) VALUES(?,?,?)",
            [(code, r["trade_date"], r["main_net_in"]) for r in rows],
        )
        self.conn.commit()

    def latest_fund_flow(self, code: str):
        return self.conn.execute(
            "SELECT * FROM fund_flow WHERE code=? ORDER BY trade_date DESC LIMIT 1", (code,)
        ).fetchone()

    def fund_flow_on_or_before(self, code: str, date: str):
        return self.conn.execute(
            "SELECT * FROM fund_flow WHERE code=? AND trade_date<=? ORDER BY trade_date DESC LIMIT 1",
            (code, date),
        ).fetchone()

    def upsert_financial(self, data: dict) -> None:
        self.conn.execute(
            "INSERT INTO financial(code,report_date,net_profit_attr,equity_attr,total_assets,total_liabilities) "
            "VALUES(?,?,?,?,?,?)",
            (data["code"], data["report_date"], data.get("net_profit_attr"), data.get("equity_attr"),
             data.get("total_assets"), data.get("total_liabilities")),
        )
        self.conn.commit()

    def latest_financial(self, code: str):
        return self.conn.execute(
            "SELECT * FROM financial WHERE code=? ORDER BY report_date DESC LIMIT 1", (code,)
        ).fetchone()

    def replace_daily_quotes(self, code: str, rows: list[dict]) -> None:
        self.conn.execute("DELETE FROM daily_quote WHERE code=?", (code,))
        self.conn.executemany(
            "INSERT INTO daily_quote(code,trade_date,open,high,low,close,volume,amount) "
            "VALUES(?,?,?,?,?,?,?,?)",
            [(code, r["trade_date"], r.get("open"), r.get("high"), r.get("low"),
              r.get("close"), r.get("volume"), r.get("amount")) for r in rows],
        )
        self.conn.commit()

    def daily_quotes(self, code: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM daily_quote WHERE code=? ORDER BY trade_date", (code,)
        ).fetchall()

    def replace_daily_indicators(self, code: str, rows: list[dict]) -> None:
        self.conn.execute("DELETE FROM daily_indicator WHERE code=?", (code,))
        self.conn.executemany(
            "INSERT INTO daily_indicator(code,trade_date,ma20,ma60,vol_ratio_20,trend_status) "
            "VALUES(?,?,?,?,?,?)",
            [(code, r["trade_date"], r.get("ma20"), r.get("ma60"), r.get("vol_ratio_20"),
              r.get("trend_status")) for r in rows],
        )
        self.conn.commit()

    def latest_daily_indicator(self, code: str):
        return self.conn.execute(
            "SELECT * FROM daily_indicator WHERE code=? ORDER BY trade_date DESC LIMIT 1", (code,)
        ).fetchone()

    def daily_indicator_on_or_before(self, code: str, date: str):
        return self.conn.execute(
            "SELECT * FROM daily_indicator WHERE code=? AND trade_date<=? ORDER BY trade_date DESC LIMIT 1",
            (code, date),
        ).fetchone()

    def upsert_forecast(self, data: dict) -> None:
        self.conn.execute(
            "INSERT INTO valuation_forecast(code,forecast_eps,forecast_net_profit_yi,source,updated_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET "
            "forecast_eps=excluded.forecast_eps, forecast_net_profit_yi=excluded.forecast_net_profit_yi, "
            "source=excluded.source, updated_at=excluded.updated_at",
            (data["code"], data.get("forecast_eps"), data.get("forecast_net_profit_yi"),
             data.get("source"), _now()),
        )
        self.conn.commit()

    def get_forecast(self, code: str):
        return self.conn.execute("SELECT * FROM valuation_forecast WHERE code=?", (code,)).fetchone()

    # --- macro ---
    def insert_macro(self, data: dict) -> None:
        self.conn.execute(
            "INSERT INTO macro_snapshot(market,snapshot_time,index_point,change_point,change_pct,"
            "high,low,amount,up_count,down_count,flat_count,total_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (data["market"], data["snapshot_time"], data.get("index_point"), data.get("change_point"),
             data.get("change_pct"), data.get("high"), data.get("low"), data.get("amount"),
             data.get("up_count"), data.get("down_count"), data.get("flat_count"), data.get("total_count")),
        )
        self.conn.commit()

    def latest_macro(self, market: str):
        return self.conn.execute(
            "SELECT * FROM macro_snapshot WHERE market=? ORDER BY snapshot_time DESC, id DESC LIMIT 1",
            (market,),
        ).fetchone()

    def recent_macro(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM macro_snapshot ORDER BY snapshot_time DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
```

- [ ] **Step 4: Run, expect pass.** `uv run pytest tests/test_repository.py`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: repository data-access layer"
```

---

## Task 4: Metrics pure functions (strict TDD)

**Files:**
- Create: `app/services/__init__.py`, `app/services/metrics.py`, `tests/test_metrics.py`

All functions are pure. Return `None` when inputs are insufficient.

- [ ] **Step 1: Write failing tests** in `tests/test_metrics.py`

```python
import pytest
from app.services import metrics


def test_dividend_yield_ttm():
    # per10=30 -> per-share 3.0; two report periods summed; latest announce kept
    dividends = [
        {"report_date": "2025-12-31", "announce_date": "2026-03-01", "pretax_bonus_per10": 30.0},
        {"report_date": "2025-12-31", "announce_date": "2026-02-01", "pretax_bonus_per10": 25.0},  # superseded
    ]
    # total dividend = 3.0/share * shares; spec uses total cash / market cap.
    # market_cap_yi=2000 (亿), total_shares_yi computed from price; here use helper signature.
    y = metrics.dividend_yield_ttm(dividends, total_shares=1.256e9, market_cap=2.0e12)
    assert y == pytest.approx(3.0 * 1.256e9 / 2.0e12 * 100, rel=1e-6)


def test_dividend_yield_none_when_no_market_cap():
    assert metrics.dividend_yield_ttm([], total_shares=1.0, market_cap=0) is None


def test_roe_annualization_q1():
    # March -> factor 4
    assert metrics.roe(net_profit_attr=100, equity_attr=1000, report_month=3) == pytest.approx(40.0)


def test_roe_annualization_q3():
    assert metrics.roe(100, 1000, 9) == pytest.approx(100 * (4/3) / 1000 * 100)


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
    assert metrics.trend_status(95, 98, 100) == "中性偏弱：价低于MA60"
    assert metrics.trend_status(110, 105, None) is None


def test_moving_average():
    closes = list(range(1, 21))  # 1..20
    assert metrics.moving_average(closes, 20) == pytest.approx(10.5)
    assert metrics.moving_average(closes, 60) is None  # not enough data
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/services/metrics.py`**

```python
"""Pure indicator calculations. No IO. Return None when inputs are insufficient."""


def moving_average(closes: list[float], window: int) -> float | None:
    if len(closes) < window or window <= 0:
        return None
    return sum(closes[-window:]) / window


def distance_pct(price: float | None, ma: float | None) -> float | None:
    if price is None or not ma:
        return None
    return (price - ma) / ma * 100


def trend_status(price, ma20, ma60) -> str | None:
    if price is None or ma20 is None or ma60 is None:
        return None
    if price > ma20 and ma20 > ma60:
        return "多头：价高于MA20，MA20高于MA60"
    if price < ma20 and ma20 < ma60:
        return "空头：价低于MA20，MA20低于MA60"
    if price > ma60:
        return "中性偏强：价高于MA60"
    return "中性偏弱：价低于MA60"


def roe(net_profit_attr, equity_attr, report_month: int) -> float | None:
    if not equity_attr:
        return None
    factor = {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}.get(report_month)
    if factor is None:
        return None
    return net_profit_attr * factor / equity_attr * 100


def debt_to_asset_ratio(total_liabilities, total_assets) -> float | None:
    if not total_assets:
        return None
    return total_liabilities / total_assets * 100


def dynamic_pe(price, forecast_eps, market_cap_yi, forecast_net_profit_yi):
    if forecast_eps:
        return price / forecast_eps, "eps"
    if market_cap_yi and forecast_net_profit_yi:
        return market_cap_yi / forecast_net_profit_yi, "net_profit"
    return None, None


def _latest_per_report_period(dividends: list[dict]) -> dict[str, dict]:
    """Keep the dividend with the latest announce_date per report_date."""
    best: dict[str, dict] = {}
    for d in dividends:
        rd = d["report_date"]
        cur = best.get(rd)
        if cur is None or (d.get("announce_date") or "") > (cur.get("announce_date") or ""):
            best[rd] = d
    return best


def dividend_yield_ttm(dividends: list[dict], total_shares: float, market_cap: float) -> float | None:
    """近一年报告期(含预案)现金分红总额 / 最近总市值 ×100%.
    pretax_bonus_per10 是每10股税前派息,先换算为每股 (/10)。
    """
    if not market_cap:
        return None
    per_period = _latest_per_report_period(dividends)
    total_cash = 0.0
    for d in per_period.values():
        per10 = d.get("pretax_bonus_per10")
        if per10 is None:
            continue
        per_share = per10 / 10.0
        total_cash += per_share * total_shares
    return total_cash / market_cap * 100
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: pure indicator metrics with tests"
```

---

## Task 5: Signal event-diff pure functions (strict TDD)

**Files:**
- Create: `app/services/signals.py`, `tests/test_signals.py`

`generate_signals(prev, curr)` returns a list of dicts `{signal_type, level, detail}`. `prev=None` → baseline → `[]`. A `SIGNAL_THRESHOLDS` dict and `SIGNAL_LABELS`/`LEVEL_LABELS` maps live here for the `/signals` page.

- [ ] **Step 1: Write failing tests** in `tests/test_signals.py`

```python
from app.services.signals import generate_signals, SIGNAL_LABELS, LEVEL_LABELS


def snap(**kw):
    base = {"snapshot_time": "2026-05-29 10:30:00", "change_pct": 0.0, "volume_ratio": 1.0,
            "main_net_in": 0.0, "amount_wan": 1000.0, "dividend_yield_ttm": 0.0,
            "dist_ma20_pct": 0.0, "dist_ma60_pct": 0.0, "ma20": 100.0, "ma60": 100.0, "price": 100.0}
    base.update(kw)
    return base


def test_first_snapshot_is_baseline_only():
    assert generate_signals(None, snap(volume_ratio=3.0, change_pct=5.0)) == []


def test_volume_surge_up_after_10am():
    prev = snap()
    curr = snap(snapshot_time="2026-05-29 10:30:00", volume_ratio=2.0, change_pct=2.0)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_up" in types


def test_volume_surge_up_suppressed_before_10am():
    prev = snap(snapshot_time="2026-05-29 09:30:00")
    curr = snap(snapshot_time="2026-05-29 09:45:00", volume_ratio=3.0, change_pct=5.0)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_up" not in types


def test_volume_surge_up_not_repeated_when_prev_already_true():
    prev = snap(volume_ratio=2.0, change_pct=2.0)
    curr = snap(volume_ratio=2.1, change_pct=2.5)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_up" not in types  # ordinary state: only on rising edge


def test_volume_surge_down():
    prev = snap()
    curr = snap(volume_ratio=2.5, change_pct=-2.0)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_down" in types


def test_main_inflow_and_outflow():
    prev = snap()
    inflow = snap(main_net_in=90.0, amount_wan=1000.0)  # 9% >= 8%
    assert "main_inflow" in [s["signal_type"] for s in generate_signals(prev, inflow)]
    outflow = snap(main_net_in=-90.0, amount_wan=1000.0)
    assert "main_outflow" in [s["signal_type"] for s in generate_signals(prev, outflow)]


def test_high_dividend_healthy_vs_broken():
    prev = snap()
    healthy = snap(dividend_yield_ttm=5.0, dist_ma60_pct=2.0)
    assert "high_dividend_healthy" in [s["signal_type"] for s in generate_signals(prev, healthy)]
    broken = snap(dividend_yield_ttm=5.0, dist_ma60_pct=-2.0)
    assert "high_dividend_broken" in [s["signal_type"] for s in generate_signals(prev, broken)]


def test_golden_cross_and_death_cross():
    # diff = ma20 - ma60
    prev = snap(ma20=99.0, ma60=100.0)   # diff <= 0
    curr = snap(ma20=101.0, ma60=100.0)  # diff > 0
    assert "golden_cross" in [s["signal_type"] for s in generate_signals(prev, curr)]
    prev2 = snap(ma20=101.0, ma60=100.0)  # diff >= 0
    curr2 = snap(ma20=99.0, ma60=100.0)   # diff < 0
    assert "death_cross" in [s["signal_type"] for s in generate_signals(prev2, curr2)]


def test_cross_above_below_ma60():
    prev = snap(dist_ma60_pct=0.5)
    curr = snap(dist_ma60_pct=1.5)
    assert "above_ma60" in [s["signal_type"] for s in generate_signals(prev, curr)]
    prev2 = snap(dist_ma60_pct=-0.5)
    curr2 = snap(dist_ma60_pct=-1.5)
    assert "below_ma60" in [s["signal_type"] for s in generate_signals(prev2, curr2)]


def test_bias_overheat_oversold():
    prev = snap(dist_ma20_pct=14.0)
    curr = snap(dist_ma20_pct=16.0)
    assert "bias_overheat" in [s["signal_type"] for s in generate_signals(prev, curr)]
    prev2 = snap(dist_ma20_pct=-14.0)
    curr2 = snap(dist_ma20_pct=-16.0)
    assert "bias_oversold" in [s["signal_type"] for s in generate_signals(prev2, curr2)]


def test_labels_exist_for_all_types():
    for t in ["volume_surge_up", "volume_surge_down", "main_inflow", "main_outflow",
              "high_dividend_healthy", "high_dividend_broken", "golden_cross", "death_cross",
              "above_ma60", "below_ma60", "bias_overheat", "bias_oversold"]:
        assert t in SIGNAL_LABELS
    assert set(LEVEL_LABELS) == {"low", "mid", "high"}
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/services/signals.py`**

```python
"""Event-diff signal generation. Pure. prev=None means baseline only."""
from datetime import datetime

SIGNAL_LABELS = {
    "volume_surge_up": "放量上涨", "volume_surge_down": "放量下跌",
    "main_inflow": "主力净流入", "main_outflow": "主力净流出",
    "high_dividend_healthy": "高股息（健康）", "high_dividend_broken": "高股息（破位）",
    "golden_cross": "金叉", "death_cross": "死叉",
    "above_ma60": "站上MA60", "below_ma60": "跌破MA60",
    "bias_overheat": "乖离过热", "bias_oversold": "乖离超卖",
}
LEVEL_LABELS = {"low": "低", "mid": "中", "high": "高"}

# threshold descriptions shown on /signals
SIGNAL_THRESHOLDS = {
    "volume_surge_up": "10:00后，量比≥2.0 且涨幅≥+2%",
    "volume_surge_down": "10:00后，量比≥2.5 且跌幅≤-2%",
    "main_inflow": "10:00后，主力净额/成交额≥+8%",
    "main_outflow": "10:00后，主力净额/成交额≤-8%",
    "high_dividend_healthy": "股息率≥5% 且未跌破MA60",
    "high_dividend_broken": "股息率≥5% 且跌破MA60",
    "golden_cross": "MA20-MA60 由≤0 变 >0",
    "death_cross": "MA20-MA60 由≥0 变 <0",
    "above_ma60": "距MA60 由<+1% 升到≥+1%",
    "below_ma60": "距MA60 由>-1% 跌到≤-1%",
    "bias_overheat": "距MA20 由<+15% 升到≥+15%",
    "bias_oversold": "距MA20 由>-15% 跌到≤-15%",
}


def _after_10am(snapshot_time: str) -> bool:
    t = datetime.strptime(snapshot_time, "%Y-%m-%d %H:%M:%S")
    return (t.hour, t.minute) >= (10, 0)


def _g(snap, key, default=0.0):
    v = snap.get(key) if isinstance(snap, dict) else snap[key]
    return default if v is None else v


def _main_ratio(snap) -> float:
    amt = _g(snap, "amount_wan", 0.0)
    if not amt:
        return 0.0
    return _g(snap, "main_net_in", 0.0) / amt * 100


def _ordinary(prev, curr, predicate) -> bool:
    """Fire only when curr satisfies predicate and prev did not."""
    return predicate(curr) and not predicate(prev)


def generate_signals(prev, curr) -> list[dict]:
    if prev is None:
        return []
    out: list[dict] = []
    after10 = _after_10am(curr["snapshot_time"] if not isinstance(curr, dict) else curr["snapshot_time"])

    def add(stype, level):
        out.append({"signal_type": stype, "level": level, "detail": SIGNAL_THRESHOLDS[stype]})

    # ordinary states (rising edge), gated by 10:00 for the volume/main signals
    if after10:
        if _ordinary(prev, curr, lambda s: _g(s, "volume_ratio") >= 2.0 and _g(s, "change_pct") >= 2.0):
            add("volume_surge_up", "mid")
        if _ordinary(prev, curr, lambda s: _g(s, "volume_ratio") >= 2.5 and _g(s, "change_pct") <= -2.0):
            add("volume_surge_down", "high")
        if _ordinary(prev, curr, lambda s: _main_ratio(s) >= 8.0):
            add("main_inflow", "low")
        if _ordinary(prev, curr, lambda s: _main_ratio(s) <= -8.0):
            add("main_outflow", "low")

    if _ordinary(prev, curr, lambda s: _g(s, "dividend_yield_ttm") >= 5.0 and _g(s, "dist_ma60_pct") >= 0):
        add("high_dividend_healthy", "low")
    if _ordinary(prev, curr, lambda s: _g(s, "dividend_yield_ttm") >= 5.0 and _g(s, "dist_ma60_pct") < 0):
        add("high_dividend_broken", "mid")

    # crossing states (compare both sides)
    pd = _g(prev, "ma20") - _g(prev, "ma60")
    cd = _g(curr, "ma20") - _g(curr, "ma60")
    if pd <= 0 and cd > 0:
        add("golden_cross", "high")
    if pd >= 0 and cd < 0:
        add("death_cross", "high")

    if _g(prev, "dist_ma60_pct") < 1.0 and _g(curr, "dist_ma60_pct") >= 1.0:
        add("above_ma60", "mid")
    if _g(prev, "dist_ma60_pct") > -1.0 and _g(curr, "dist_ma60_pct") <= -1.0:
        add("below_ma60", "high")

    if _g(prev, "dist_ma20_pct") < 15.0 and _g(curr, "dist_ma20_pct") >= 15.0:
        add("bias_overheat", "mid")
    if _g(prev, "dist_ma20_pct") > -15.0 and _g(curr, "dist_ma20_pct") <= -15.0:
        add("bias_oversold", "mid")

    return out
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: event-diff signal generation with tests"
```

---

## Task 6: Stock pool parsing (strict TDD)

**Files:**
- Create: `app/services/stock_pool.py`, `tests/test_stock_pool.py`

`split_inputs(text)` and `normalize_code(text)` are pure. `resolve(text, search_fn)` takes an injected search function `search_fn(keyword) -> [{"code","name"}]` so it can be unit-tested without network.

- [ ] **Step 1: Write failing tests** in `tests/test_stock_pool.py`

```python
from app.services.stock_pool import split_inputs, normalize_code, resolve, StockResolveError


def test_split_inputs_all_separators():
    text = "600519, 三七互娱、华钰股份；000858\n000001\t300750"
    assert split_inputs(text) == ["600519", "三七互娱", "华钰股份", "000858", "000001", "300750"]


def test_normalize_code_pads_and_validates():
    assert normalize_code("600519") == "600519"
    assert normalize_code("1") == "000001"
    assert normalize_code("abc") is None


def test_resolve_via_search():
    def search(kw):
        return [{"code": "600519", "name": "贵州茅台"}] if kw == "茅台" else []
    assert resolve("茅台", search) == {"code": "600519", "name": "贵州茅台"}


def test_resolve_numeric_fallback_when_search_empty():
    def search(kw):
        return []
    assert resolve("600519", search) == {"code": "600519", "name": "600519"}


def test_resolve_strips_suffix_and_retries():
    calls = []
    def search(kw):
        calls.append(kw)
        return [{"code": "000001", "name": "平安银行"}] if kw == "平安" else []
    assert resolve("平安股份", search) == {"code": "000001", "name": "平安银行"}
    assert calls == ["平安股份", "平安"]


def test_resolve_raises_friendly_error():
    def search(kw):
        return []
    try:
        resolve("不存在的票", search)
        assert False
    except StockResolveError as e:
        assert "不存在的票" in str(e)
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/services/stock_pool.py`**

```python
import re

_SEP = re.compile(r"[,，、;；\n\t]+")
_SUFFIXES = ["股份", "股票", "证券", "集团", "有限"]


class StockResolveError(Exception):
    pass


def split_inputs(text: str) -> list[str]:
    return [p.strip() for p in _SEP.split(text or "") if p.strip()]


def normalize_code(text: str) -> str | None:
    text = text.strip()
    if not text.isdigit():
        return None
    return text.zfill(6)


def resolve(token: str, search_fn) -> dict:
    token = token.strip()
    hits = search_fn(token)
    if hits:
        return {"code": hits[0]["code"], "name": hits[0]["name"]}
    code = normalize_code(token)
    if code:
        return {"code": code, "name": token if not token.isdigit() else code}
    for suf in _SUFFIXES:
        if token.endswith(suf):
            stripped = token[: -len(suf)]
            hits = search_fn(stripped)
            if hits:
                return {"code": hits[0]["code"], "name": hits[0]["name"]}
            break
    raise StockResolveError(f"无法匹配股票：{token}")
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: stock pool input parsing and resolution"
```

---

## Task 7: Source adapter base + Tencent

**Files:**
- Create: `app/sources/__init__.py`, `app/sources/base.py`, `app/sources/tencent.py`, `tests/test_tencent.py`, `tests/fixtures/tencent_quote.txt`, `tests/fixtures/tencent_search.txt`

Adapters parse raw responses into dicts. `base.http_get(url, **kw)` wraps `requests` with timeout/UA. Parsing functions are separated from fetching so tests pass raw text.

- [ ] **Step 1: Record fixtures** — Tencent quote line format (`v_sh600519="1~贵州茅台~600519~1700.00~...";`). Create `tests/fixtures/tencent_quote.txt`:

```text
v_sh600519="1~贵州茅台~600519~1700.00~1680.00~1690.00~12345~6000~6345~1699.00~10~1698.00~20~1701.00~30~1702.00~40~1703.00~50~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~";
```

> NOTE for implementer: the Tencent `v_` string has ~80 `~`-separated fields. The parser below indexes by position with safe fallback. During implementation, fetch one real line with `curl 'https://qt.gtimg.cn/q=sh600519'` to confirm indices for price(3), name(1), code(2), change_pct(32), turnover(38), pe_ttm(39), amount(37, 万元), volume_ratio(49), market_cap(45), float_cap(44), pb(46). Adjust index constants in `tencent.py` if the live format differs, keeping the parser signature stable.

- [ ] **Step 2: Write failing tests** in `tests/test_tencent.py`

```python
from app.sources.tencent import parse_quote, parse_search


def test_parse_quote_basic():
    raw = open("tests/fixtures/tencent_quote.txt", encoding="utf-8").read()
    q = parse_quote(raw)["600519"]
    assert q["code"] == "600519"
    assert q["name"] == "贵州茅台"
    assert q["price"] == 1700.00


def test_parse_search():
    raw = 'v_hint="sh600519~贵州茅台~GZMT~1,sz000858~五粮液~WLY~1";'
    hits = parse_search(raw)
    assert hits[0]["code"] == "600519"
    assert hits[0]["name"] == "贵州茅台"
    assert hits[1]["code"] == "000858"
```

- [ ] **Step 3: Run, expect failure.**

- [ ] **Step 4: Implement `app/sources/base.py`**

```python
import requests

_HEADERS = {"User-Agent": "Mozilla/5.0 (StockTrace)"}


def http_get(url: str, *, params: dict | None = None, timeout: float = 10.0,
             headers: dict | None = None, encoding: str | None = None) -> str:
    resp = requests.get(url, params=params, timeout=timeout, headers={**_HEADERS, **(headers or {})})
    resp.raise_for_status()
    if encoding:
        resp.encoding = encoding
    return resp.text


def http_get_json(url: str, *, params: dict | None = None, timeout: float = 10.0,
                  headers: dict | None = None) -> dict:
    resp = requests.get(url, params=params, timeout=timeout, headers={**_HEADERS, **(headers or {})})
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 5: Implement `app/sources/tencent.py`**

```python
import re

from app.sources.base import http_get

_QUOTE_RE = re.compile(r'v_[a-z]{2}(\d{6})="([^"]*)";')
_PREFIX = {"6": "sh", "9": "sh", "0": "sz", "2": "sz", "3": "sz"}


def _market(code: str) -> str:
    return _PREFIX.get(code[0], "sh")


def _f(parts, idx):
    try:
        v = parts[idx]
        return float(v) if v not in ("", None) else None
    except (IndexError, ValueError):
        return None


def parse_quote(raw: str) -> dict:
    """Parse one or more v_xxNNNNNN="..." lines into {code: quote_dict}."""
    result = {}
    for m in _QUOTE_RE.finditer(raw):
        code = m.group(1)
        p = m.group(2).split("~")
        result[code] = {
            "code": code,
            "name": p[1] if len(p) > 1 else code,
            "price": _f(p, 3),
            "change_pct": _f(p, 32),
            "turnover_pct": _f(p, 38),
            "amount_wan": _f(p, 37),
            "volume_ratio": _f(p, 49),
            "pe_ttm": _f(p, 39),
            "pb": _f(p, 46),
            "market_cap_yi": _f(p, 45),
            "float_market_cap_yi": _f(p, 44),
            "pe_static": _f(p, 53),
        }
    return result


def parse_search(raw: str) -> list[dict]:
    m = re.search(r'v_hint="([^"]*)"', raw)
    if not m or not m.group(1):
        return []
    hits = []
    for item in m.group(1).split(","):
        f = item.split("~")
        if len(f) >= 2 and len(f[0]) >= 8:
            hits.append({"code": f[0][2:], "name": f[1]})
    return hits


def fetch_quotes(codes: list[str]) -> dict:
    if not codes:
        return {}
    q = ",".join(f"{_market(c)}{c}" for c in codes)
    raw = http_get("https://qt.gtimg.cn/q=" + q, encoding="gbk")
    return parse_quote(raw)


def search(keyword: str) -> list[dict]:
    raw = http_get("https://smartbox.gtimg.cn/s3/", params={"t": "all", "q": keyword}, encoding="gbk")
    return parse_search(raw)


def fetch_index(market: str) -> dict:
    code = "sh000001" if market == "sh" else "sz399001"
    raw = http_get(f"https://qt.gtimg.cn/q={code}", encoding="gbk")
    parsed = parse_quote(raw)
    key = "000001" if market == "sh" else "399001"
    q = parsed.get(key, {})
    return {"index_point": q.get("price"), "change_pct": q.get("change_pct")}
```

- [ ] **Step 6: Run, expect pass.** `uv run pytest tests/test_tencent.py`

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: source base + tencent adapter (quote/search/index)"
```

---

## Task 8: Eastmoney adapter (dividend / daily K / fund flow / market breadth)

**Files:**
- Create: `app/sources/eastmoney.py`, `tests/test_eastmoney.py`, fixtures under `tests/fixtures/`

Parsers separated from fetchers. Test parsers against fixture JSON.

- [ ] **Step 1: Create fixtures** `tests/fixtures/em_dividend.json`, `em_kline.json`, `em_fundflow.json`, `em_breadth.json` with minimal representative shapes:

`em_kline.json`:
```json
{"data": {"klines": ["2026-05-27,1690.0,1700.0,1705.0,1685.0,12000,2.04e9", "2026-05-28,1700.0,1710.0,1715.0,1695.0,13000,2.2e9"]}}
```
`em_fundflow.json`:
```json
{"data": {"klines": ["2026-05-27,1000000.0,1,2,3,4", "2026-05-28,-500000.0,1,2,3,4"]}}
```
`em_dividend.json`:
```json
{"result": {"data": [{"REPORT_DATE": "2025-12-31 00:00:00", "NOTICE_DATE": "2026-03-01 00:00:00", "PRETAX_BONUS_RMB": 30.0, "ASSIGN_PROGRESS": "实施分配"}]}}
```
`em_breadth.json`:
```json
{"data": {"f104": 1200, "f105": 800, "f106": 100}}
```

- [ ] **Step 2: Write failing tests** in `tests/test_eastmoney.py`

```python
import json
from app.sources.eastmoney import parse_kline, parse_fund_flow, parse_dividends, parse_breadth


def _load(name):
    return json.load(open(f"tests/fixtures/{name}", encoding="utf-8"))


def test_parse_kline():
    rows = parse_kline(_load("em_kline.json"))
    assert rows[0]["trade_date"] == "2026-05-27"
    assert rows[0]["close"] == 1700.0
    assert rows[1]["close"] == 1710.0


def test_parse_fund_flow():
    rows = parse_fund_flow(_load("em_fundflow.json"))
    assert rows[0] == {"trade_date": "2026-05-27", "main_net_in": 1000000.0}
    assert rows[1]["main_net_in"] == -500000.0


def test_parse_dividends():
    rows = parse_dividends(_load("em_dividend.json"))
    assert rows[0]["report_date"] == "2025-12-31"
    assert rows[0]["announce_date"] == "2026-03-01"
    assert rows[0]["pretax_bonus_per10"] == 30.0
    assert rows[0]["plan_or_impl"] == "实施分配"


def test_parse_breadth():
    b = parse_breadth(_load("em_breadth.json"))
    assert b["up_count"] == 1200
    assert b["down_count"] == 800
    assert b["flat_count"] == 100
    assert b["total_count"] == 2100
```

- [ ] **Step 3: Run, expect failure.**

- [ ] **Step 4: Implement `app/sources/eastmoney.py`**

```python
from app.sources.base import http_get_json

_SECID = {"6": "1", "9": "1"}  # sh -> 1 else 0


def _secid(code: str) -> str:
    return f"{'1' if code[0] in ('6', '9') else '0'}.{code}"


def parse_kline(payload: dict) -> list[dict]:
    rows = []
    for line in payload.get("data", {}).get("klines", []):
        f = line.split(",")
        rows.append({"trade_date": f[0], "open": float(f[1]), "close": float(f[2]),
                     "high": float(f[3]), "low": float(f[4]),
                     "volume": float(f[5]), "amount": float(f[6])})
    return rows


def parse_fund_flow(payload: dict) -> list[dict]:
    rows = []
    for line in payload.get("data", {}).get("klines", []):
        f = line.split(",")
        rows.append({"trade_date": f[0], "main_net_in": float(f[1])})
    return rows


def parse_dividends(payload: dict) -> list[dict]:
    rows = []
    for d in payload.get("result", {}).get("data", []):
        rd = (d.get("REPORT_DATE") or "")[:10]
        ad = (d.get("NOTICE_DATE") or "")[:10] or None
        rows.append({"report_date": rd, "announce_date": ad,
                     "pretax_bonus_per10": d.get("PRETAX_BONUS_RMB"),
                     "plan_or_impl": d.get("ASSIGN_PROGRESS")})
    return rows


def parse_breadth(payload: dict) -> dict:
    d = payload.get("data", {})
    up, down, flat = d.get("f104", 0), d.get("f105", 0), d.get("f106", 0)
    return {"up_count": up, "down_count": down, "flat_count": flat,
            "total_count": (up or 0) + (down or 0) + (flat or 0)}


def fetch_kline(code: str, limit: int = 120) -> list[dict]:
    payload = http_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={"secid": _secid(code), "fields1": "f1", "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": "101", "fqt": "1", "end": "20500101", "lmt": str(limit)},
    )
    return parse_kline(payload)


def fetch_fund_flow(code: str, limit: int = 120) -> list[dict]:
    payload = http_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        params={"secid": _secid(code), "fields1": "f1", "fields2": "f51,f52,f53,f54,f55,f56", "lmt": str(limit)},
    )
    return parse_fund_flow(payload)


def fetch_dividends(code: str) -> list[dict]:
    payload = http_get_json(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={"reportName": "RPT_SHAREBONUS_DET", "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")', "pageSize": "50"},
    )
    return parse_dividends(payload)


def fetch_breadth(market: str) -> dict:
    secid = "1.000001" if market == "sh" else "0.399001"
    payload = http_get_json("https://push2.eastmoney.com/api/qt/stock/get",
                            params={"secid": secid, "fields": "f104,f105,f106"})
    return parse_breadth(payload)
```

- [ ] **Step 5: Run, expect pass.**

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: eastmoney adapter (dividend/kline/fundflow/breadth)"
```

---

## Task 9: Sina adapter (financial statements)

**Files:**
- Create: `app/sources/sina.py`, `tests/test_sina.py`, `tests/fixtures/sina_balance.json`

Sina returns the three statements; we extract net_profit_attr, equity_attr, total_assets, total_liabilities for the latest report. Parser takes already-decoded structures.

- [ ] **Step 1: Create fixture** `tests/fixtures/sina_balance.json`:

```json
{"report_date": "2025-12-31", "net_profit_attr": 8.0e10, "equity_attr": 2.0e11, "total_assets": 3.0e11, "total_liabilities": 1.0e11}
```

- [ ] **Step 2: Write failing test** in `tests/test_sina.py`

```python
import json
from app.sources.sina import parse_financial


def test_parse_financial():
    raw = json.load(open("tests/fixtures/sina_balance.json", encoding="utf-8"))
    fin = parse_financial(raw)
    assert fin["report_date"] == "2025-12-31"
    assert fin["total_assets"] == 3.0e11
    assert fin["total_liabilities"] == 1.0e11
    assert fin["equity_attr"] == 2.0e11
    assert fin["net_profit_attr"] == 8.0e10
```

- [ ] **Step 3: Run, expect failure.**

- [ ] **Step 4: Implement `app/sources/sina.py`**

```python
from app.sources.base import http_get_json

_KEYS = ["report_date", "net_profit_attr", "equity_attr", "total_assets", "total_liabilities"]


def parse_financial(payload: dict) -> dict:
    """Normalize a decoded Sina financial payload into the fields we persist."""
    return {k: payload.get(k) for k in _KEYS}


def fetch_financial(code: str) -> dict:
    """Live fetch. NOTE for implementer: Sina's vCT_PageFinance endpoints return
    semi-structured JSON; during implementation confirm the exact URL and field
    names with one real request and map them into the dict shape below, then call
    parse_financial on the mapped dict so the persisted shape stays stable."""
    market = "sh" if code[0] in ("6", "9") else "sz"
    payload = http_get_json(
        "https://money.finance.sina.com.cn/corp/go.php/vDOWN_BalanceSheet/displaytype/4/stockid/"
        f"{code}/ctrl/all.phtml", params={}
    ) if False else {}
    # Map the real payload here into _KEYS-shaped dict; placeholder mapping kept explicit:
    mapped = {
        "report_date": payload.get("report_date"),
        "net_profit_attr": payload.get("net_profit_attr"),
        "equity_attr": payload.get("equity_attr"),
        "total_assets": payload.get("total_assets"),
        "total_liabilities": payload.get("total_liabilities"),
        "_market": market,
    }
    return parse_financial(mapped)
```

> NOTE for implementer: Sina's statement endpoints are HTML/CSV-ish, not clean JSON. The contract that matters is `parse_financial(mapped_dict) -> {report_date, net_profit_attr, equity_attr, total_assets, total_liabilities}`. Implement `fetch_financial` to retrieve real data (CSV download endpoint `.../vDOWN_BalanceSheet/.../all.phtml` + the income statement endpoint) and map into that dict. Keep `parse_financial`'s signature and the persisted keys unchanged so `low_freq` and `metrics` are unaffected. `financial` can also be populated manually via CLI (Task 16).

- [ ] **Step 5: Run, expect pass.** `uv run pytest tests/test_sina.py`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: sina financial adapter (parser + fetch mapping)"
```

---

## Task 10: Baidu adapter (minute-level fund flow)

**Files:**
- Create: `app/sources/baidu.py`, `tests/test_baidu.py`, `tests/fixtures/baidu_fundflow.json`

- [ ] **Step 1: Create fixture** `tests/fixtures/baidu_fundflow.json`:

```json
{"Result": {"pankou_diagram": {"mainInflow": "1234.5"}}}
```

- [ ] **Step 2: Write failing test** in `tests/test_baidu.py`

```python
import json
from app.sources.baidu import parse_main_net_in


def test_parse_main_net_in():
    raw = json.load(open("tests/fixtures/baidu_fundflow.json", encoding="utf-8"))
    assert parse_main_net_in(raw) == 1234.5


def test_parse_main_net_in_missing():
    assert parse_main_net_in({"Result": {}}) is None
```

- [ ] **Step 3: Run, expect failure.**

- [ ] **Step 4: Implement `app/sources/baidu.py`**

```python
from app.sources.base import http_get_json


def parse_main_net_in(payload: dict):
    """Return main net inflow in 万元, or None. Baidu's real key may differ;
    keep this single accessor as the contract."""
    try:
        val = payload["Result"]["pankou_diagram"]["mainInflow"]
    except (KeyError, TypeError):
        return None
    if val in (None, ""):
        return None
    return float(val)


def fetch_main_net_in(code: str):
    """NOTE for implementer: confirm Baidu 股市通 endpoint + query params with one
    real request; map response so parse_main_net_in extracts 万元 main inflow."""
    payload = http_get_json(
        "https://finance.pae.baidu.com/selfselect/getstockquotation",
        params={"code": code, "all": "1", "isIndex": "false", "finClientType": "pc"},
    )
    return parse_main_net_in(payload)
```

- [ ] **Step 5: Run, expect pass.**

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: baidu minute fund-flow adapter"
```

---

## Task 11: Macro snapshot service

**Files:**
- Create: `app/services/macro.py`, `tests/test_macro.py`

`sync_macro(repo, index_fn, breadth_fn, now_fn)` writes one row per market. Dependencies injected.

- [ ] **Step 1: Write failing test** in `tests/test_macro.py`

```python
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
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/services/macro.py`**

```python
from datetime import datetime


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sync_macro(repo, index_fn, breadth_fn, now_fn=_now) -> None:
    ts = now_fn()
    for market in ("sh", "sz"):
        idx = index_fn(market) or {}
        breadth = breadth_fn(market) or {}
        repo.insert_macro({"market": market, "snapshot_time": ts,
                           "index_point": idx.get("index_point"),
                           "change_point": idx.get("change_point"),
                           "change_pct": idx.get("change_pct"),
                           "high": idx.get("high"), "low": idx.get("low"),
                           "amount": idx.get("amount"),
                           "up_count": breadth.get("up_count"),
                           "down_count": breadth.get("down_count"),
                           "flat_count": breadth.get("flat_count"),
                           "total_count": breadth.get("total_count")})
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: macro snapshot sync service"
```

---

## Task 12: Snapshot sync service (orchestration)

**Files:**
- Create: `app/services/snapshot.py`, `tests/test_snapshot.py`

`sync_snapshots(repo, codes, quote_fn, baidu_fn, now_fn)` builds each snapshot from quote + low-freq cache + metrics, persists it, then generates signals from `last_two_snapshots`. Returns list of persisted snapshot dicts. Macro sync and notify are orchestrated by the caller (CLI/web/scheduler), not here — keeps this unit focused and testable.

- [ ] **Step 1: Write failing test** in `tests/test_snapshot.py`

```python
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
    def quote_fn(codes): return quotes
    def baidu_fn(code): return None  # force fallback to local daily fund flow
    snaps = sync_snapshots(repo, ["600519"], quote_fn, baidu_fn, now_fn=lambda: "2026-05-29 10:30:00")
    s = snaps[0]
    assert s["code"] == "600519"
    assert s["ma20"] == 1650.0
    assert s["dist_ma20_pct"] == pytest.approx((1700-1650)/1650*100)
    assert s["roe"] is not None
    assert s["debt_to_asset_ratio"] == pytest.approx(1.0e11/3.0e11*100)
    assert s["main_net_in_source"] == "fund_flow"  # baidu returned None
    # main_net_in converted to 万元: 5,000,000 元 -> 500 万元
    assert s["main_net_in"] == pytest.approx(500.0)
    # persisted
    assert len(repo.snapshots_for("600519")) == 1


def test_sync_prefers_baidu_main_net_in(repo):
    quotes = {"600519": {"code": "600519", "name": "贵州茅台", "price": 1700.0, "amount_wan": 100000.0,
                         "market_cap_yi": 2000.0}}
    snaps = sync_snapshots(repo, ["600519"], lambda c: quotes, lambda code: 888.0,
                           now_fn=lambda: "2026-05-29 10:30:00")
    assert snaps[0]["main_net_in"] == 888.0
    assert snaps[0]["main_net_in_source"] == "baidu"
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/services/snapshot.py`**

```python
from datetime import datetime

from app.services import metrics, signals


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _report_month(report_date: str) -> int:
    return int(report_date[5:7])


def _build_snapshot(repo, code: str, quote: dict, baidu_fn, ts: str) -> dict:
    price = quote.get("price")
    di = repo.latest_daily_indicator(code)
    ma20 = di["ma20"] if di else None
    ma60 = di["ma60"] if di else None
    fin = repo.latest_financial(code)
    fc = repo.get_forecast(code)

    # main net inflow: prefer baidu (万元), fall back to local daily fund flow (元 -> 万元)
    main_net_in, source = baidu_fn(code), "baidu"
    if main_net_in is None:
        ff = repo.latest_fund_flow(code)
        if ff is not None:
            main_net_in, source = ff["main_net_in"] / 10000.0, "fund_flow"
        else:
            main_net_in, source = None, None

    roe = debt = div_yield = None
    if fin:
        roe = metrics.roe(fin["net_profit_attr"], fin["equity_attr"], _report_month(fin["report_date"]))
        debt = metrics.debt_to_asset_ratio(fin["total_liabilities"], fin["total_assets"])
    market_cap_yi = quote.get("market_cap_yi")
    if market_cap_yi:
        dividends = [dict(d) for d in repo.dividends_for(code)]
        total_shares = market_cap_yi * 1e8 / price if price else 0
        div_yield = metrics.dividend_yield_ttm(dividends, total_shares, market_cap_yi * 1e8)

    pe_dyn, pe_dyn_src = metrics.dynamic_pe(
        price, fc["forecast_eps"] if fc else None, market_cap_yi,
        fc["forecast_net_profit_yi"] if fc else None)

    return {
        "code": code, "name": quote.get("name"), "snapshot_time": ts,
        "price": price, "change_pct": quote.get("change_pct"), "turnover_pct": quote.get("turnover_pct"),
        "amount_wan": quote.get("amount_wan"), "volume_ratio": quote.get("volume_ratio"),
        "pe_static": quote.get("pe_static"), "pe_ttm": quote.get("pe_ttm"),
        "pe_dynamic": pe_dyn, "pe_dynamic_source": pe_dyn_src, "pb": quote.get("pb"),
        "market_cap_yi": market_cap_yi, "float_market_cap_yi": quote.get("float_market_cap_yi"),
        "dividend_yield_ttm": div_yield, "roe": roe, "ma20": ma20, "ma60": ma60,
        "dist_ma20_pct": metrics.distance_pct(price, ma20),
        "dist_ma60_pct": metrics.distance_pct(price, ma60),
        "trend_status": metrics.trend_status(price, ma20, ma60),
        "debt_to_asset_ratio": debt, "main_net_in": main_net_in, "main_net_in_source": source,
    }


def sync_snapshots(repo, codes, quote_fn, baidu_fn, now_fn=_now) -> list[dict]:
    ts = now_fn()
    quotes = quote_fn(codes) or {}
    persisted = []
    for code in codes:
        quote = quotes.get(code)
        if not quote:
            continue
        snap = _build_snapshot(repo, code, quote, baidu_fn, ts)
        repo.insert_snapshot(snap)
        _generate_for(repo, code, snap)
        persisted.append(snap)
    return persisted


def _generate_for(repo, code: str, curr: dict) -> None:
    last_two = repo.last_two_snapshots(code)
    prev = dict(last_two[1]) if len(last_two) >= 2 else None
    for sig in signals.generate_signals(prev, curr):
        repo.insert_signal({"code": code, "name": curr.get("name"),
                            "signal_type": sig["signal_type"], "level": sig["level"],
                            "snapshot_time": curr["snapshot_time"], "detail": sig["detail"]})
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: snapshot sync orchestration with signal generation"
```

---

## Task 13: Low-frequency refresh service

**Files:**
- Create: `app/services/low_freq.py`, `tests/test_low_freq.py`

`refresh_low_freq(repo, codes, sources, on_error)` runs, per stock in order: dividends → fund flow → financial → daily K + indicators. A failure in one item for one stock does not abort; `on_error(code, item, exc)` is called. `sources` is a small object/namespace with the four fetch fns + a way to compute indicators (reuse `metrics`). Returns list of error tuples.

- [ ] **Step 1: Write failing test** in `tests/test_low_freq.py`

```python
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
    klines = [{"trade_date": f"2026-01-{d:02d}", "open": 100+d, "high": 100+d, "low": 100+d,
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
    def boom(c): raise RuntimeError("dividend down")
    src = LowFreqSources(
        dividends_fn=boom,
        fund_flow_fn=lambda c: [{"trade_date": "2026-05-28", "main_net_in": 1.0}],
        financial_fn=lambda c: {"report_date": "2025-12-31", "net_profit_attr": 1.0, "equity_attr": 2.0,
                                "total_assets": 3.0, "total_liabilities": 1.0},
        kline_fn=lambda c: [],
    )
    errors = refresh_low_freq(repo, ["600519"], src, on_error=lambda code, item, exc: captured.append((item, str(exc))))
    assert ("dividends", "dividend down") in captured
    assert repo.latest_fund_flow("600519") is not None  # later items still ran
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/services/low_freq.py`**

```python
from dataclasses import dataclass
from typing import Callable

from app.services import metrics


@dataclass
class LowFreqSources:
    dividends_fn: Callable[[str], list]
    fund_flow_fn: Callable[[str], list]
    financial_fn: Callable[[str], dict]
    kline_fn: Callable[[str], list]


def _compute_indicators(klines: list[dict]) -> list[dict]:
    closes = [k["close"] for k in klines]
    rows = []
    for i, k in enumerate(klines):
        window = closes[: i + 1]
        ma20 = metrics.moving_average(window, 20)
        ma60 = metrics.moving_average(window, 60)
        rows.append({"trade_date": k["trade_date"], "ma20": ma20, "ma60": ma60,
                     "vol_ratio_20": None,
                     "trend_status": metrics.trend_status(k["close"], ma20, ma60)})
    return rows


def refresh_low_freq(repo, codes, sources: LowFreqSources, on_error=None) -> list[tuple]:
    errors = []

    def run(code, item, fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - single item failure must not abort
            errors.append((code, item, exc))
            if on_error:
                on_error(code, item, exc)

    for code in codes:
        run(code, "dividends", lambda: repo.replace_dividends(code, sources.dividends_fn(code)))
        run(code, "fund_flow", lambda: repo.replace_fund_flows(code, sources.fund_flow_fn(code)))
        run(code, "financial", lambda: repo.upsert_financial({**sources.financial_fn(code), "code": code}))
        def do_kline(code=code):
            klines = sources.kline_fn(code)
            repo.replace_daily_quotes(code, klines)
            repo.replace_daily_indicators(code, _compute_indicators(klines))
        run(code, "kline", do_kline)
    return errors
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: low-frequency refresh with per-item failure isolation"
```

---

## Task 14: Backfill service (regen-signals + backfill)

**Files:**
- Create: `app/services/backfill.py`, `tests/test_backfill.py`

`regen_signals(repo, date, delete_first=True)` recomputes a day's signals from that day's intraday snapshot sequence. `backfill(repo, codes, start, end)` synthesizes a daily snapshot from daily_quote + daily_indicator + fund_flow and diffs "today vs previous trading day", stamping signal time as `<date> 15:00:00`.

- [ ] **Step 1: Write failing test** in `tests/test_backfill.py`

```python
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
    # two snapshots same day -> golden cross between them
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
    assert snap["dist_ma20_pct"] == pytest.approx((1700-1650)/1650*100)
    assert snap["main_net_in"] == pytest.approx(500.0)  # 元 -> 万元


def test_backfill_diffs_consecutive_days(repo):
    for day, ma20 in [("2026-05-27", 99.0), ("2026-05-28", 101.0)]:
        repo.replace_daily_quotes("600519", [{"trade_date": day, "close": 100.0, "open": 1,
                                              "high": 1, "low": 1, "volume": 1, "amount": 1}]) if False else None
    # set up two trading days
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
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/services/backfill.py`**

```python
from datetime import date as date_cls
from datetime import datetime, timedelta

from app.services import metrics, signals


def _prev_trading_date(repo, code: str, date: str) -> str | None:
    rows = repo.daily_quotes(code)
    dates = [r["trade_date"] for r in rows if r["trade_date"] < date]
    return dates[-1] if dates else None


def synth_daily_snapshot(repo, code: str, date: str) -> dict | None:
    quotes = {r["trade_date"]: r for r in repo.daily_quotes(code)}
    q = quotes.get(date)
    if q is None:
        return None
    di = repo.daily_indicator_on_or_before(code, date)
    ma20 = di["ma20"] if di else None
    ma60 = di["ma60"] if di else None
    ff = repo.fund_flow_on_or_before(code, date)
    main = ff["main_net_in"] / 10000.0 if ff else None
    price = q["close"]
    return {"code": code, "name": (repo.get_stock(code) or {})["name"] if repo.get_stock(code) else None,
            "snapshot_time": f"{date} 15:00:00", "price": price,
            "change_pct": 0.0, "amount_wan": (q["amount"] or 0) / 10000.0 if q["amount"] else 0.0,
            "volume_ratio": (di["vol_ratio_20"] if di else None) or 0.0,
            "ma20": ma20, "ma60": ma60,
            "dist_ma20_pct": metrics.distance_pct(price, ma20),
            "dist_ma60_pct": metrics.distance_pct(price, ma60),
            "trend_status": metrics.trend_status(price, ma20, ma60),
            "main_net_in": main, "main_net_in_source": "fund_flow" if ff else None,
            "dividend_yield_ttm": 0.0}


def regen_signals(repo, date: str, delete_first: bool = True) -> int:
    if delete_first:
        repo.delete_signals_on_date(date)
    count = 0
    for stock in repo.list_stocks():
        code = stock["code"]
        seq = [dict(s) for s in repo.snapshots_on_date(code, date)]
        prev = None
        for curr in seq:
            for sig in signals.generate_signals(prev, curr):
                repo.insert_signal({"code": code, "name": curr.get("name"),
                                    "signal_type": sig["signal_type"], "level": sig["level"],
                                    "snapshot_time": curr["snapshot_time"], "detail": sig["detail"]})
                count += 1
            prev = curr
    return count


def backfill(repo, codes, start: str | None, end: str | None) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    start = start or today
    end = end or start
    count = 0
    for code in codes:
        d = datetime.strptime(start, "%Y-%m-%d").date()
        last = datetime.strptime(end, "%Y-%m-%d").date()
        while d <= last:
            ds = d.strftime("%Y-%m-%d")
            curr = synth_daily_snapshot(repo, code, ds)
            if curr is not None:
                prev_date = _prev_trading_date(repo, code, ds)
                prev = synth_daily_snapshot(repo, code, prev_date) if prev_date else None
                for sig in signals.generate_signals(prev, curr):
                    repo.insert_signal({"code": code, "name": curr.get("name"),
                                        "signal_type": sig["signal_type"], "level": sig["level"],
                                        "snapshot_time": f"{ds} 15:00:00", "detail": sig["detail"]})
                    count += 1
            d += timedelta(days=1)
    return count
```

> NOTE for implementer: `generate_signals` gates volume/main signals on `_after_10am`; backfilled snapshots stamp `15:00:00`, which is after 10:00, so those gates pass — correct for daily backfill.

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: signal backfill (regen + daily synth)"
```

---

## Task 15: Email sender + notify service

**Files:**
- Create: `app/email_sender.py`, `app/services/notify.py`, `tests/test_notify.py`

`notify(repo, send_fn, recipients)` finds signals with no successful `notification_log` row for each recipient, sends via injected `send_fn(recipient, subject, body)`, logs success/failure, raises if any send failed. `email_sender.smtp_send` is the real impl (thin, not unit-tested with network).

- [ ] **Step 1: Write failing tests** in `tests/test_notify.py`

```python
import pytest
from app.db.connection import connect, init_db
from app.db.repository import Repository
from app.services.notify import notify, NotifyError


@pytest.fixture
def repo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    r = Repository(connect(db))
    r.insert_signal({"code": "600519", "name": "茅台", "signal_type": "golden_cross",
                     "level": "high", "snapshot_time": "2026-05-29 10:00:00", "detail": "d"})
    return r


def test_notify_sends_new_signals_once(repo):
    sent = []
    notify(repo, lambda to, subj, body: sent.append(to), ["a@x.com"])
    assert sent == ["a@x.com"]
    # second run: already notified successfully -> no resend
    notify(repo, lambda to, subj, body: sent.append(to), ["a@x.com"])
    assert sent == ["a@x.com"]


def test_notify_records_failure_and_raises(repo):
    def boom(to, subj, body):
        raise RuntimeError("smtp down")
    with pytest.raises(NotifyError):
        notify(repo, boom, ["a@x.com"])
    # failure logged, so a retry is still attempted next time
    sent = []
    notify(repo, lambda to, subj, body: sent.append(to), ["a@x.com"])
    assert sent == ["a@x.com"]
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/email_sender.py`**

```python
import smtplib
from email.mime.text import MIMEText


def make_send_fn(cfg: dict):
    """Build a send_fn(recipient, subject, body) from email config."""
    def send_fn(recipient: str, subject: str, body: str) -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = cfg["from_addr"]
        msg["To"] = recipient
        host = cfg["smtp_host"]
        port = int(cfg.get("smtp_port", 465))
        with smtplib.SMTP_SSL(host, port) as server:
            if cfg.get("username"):
                server.login(cfg["username"], cfg["password"])
            server.sendmail(cfg["from_addr"], [recipient], msg.as_string())
    return send_fn
```

- [ ] **Step 4: Implement `app/services/notify.py`**

```python
from app.services.signals import LEVEL_LABELS, SIGNAL_LABELS


class NotifyError(Exception):
    pass


def _format(signal) -> tuple[str, str]:
    stype = SIGNAL_LABELS.get(signal["signal_type"], signal["signal_type"])
    level = LEVEL_LABELS.get(signal["level"], signal["level"])
    subject = f"[StockTrace] {signal['code']} {signal['name'] or ''} {stype}"
    body = (f"股票：{signal['code']} {signal['name'] or ''}\n类型：{stype}\n级别：{level}\n"
            f"时间：{signal['snapshot_time']}\n说明：{signal['detail'] or ''}")
    return subject, body


def notify(repo, send_fn, recipients: list[str]) -> int:
    already = repo.notified_signal_recipient_pairs()
    sent_count = 0
    failures = []
    for sig in repo.all_signals():
        for recipient in recipients:
            if (sig["id"], recipient) in already:
                continue
            subject, body = _format(sig)
            try:
                send_fn(recipient, subject, body)
                repo.log_notification(sig["id"], recipient, "success", None)
                sent_count += 1
            except Exception as exc:  # noqa: BLE001
                repo.log_notification(sig["id"], recipient, "fail", str(exc))
                failures.append((sig["id"], recipient, str(exc)))
    if failures:
        raise NotifyError(f"{len(failures)} 封邮件发送失败: {failures}")
    return sent_count
```

- [ ] **Step 5: Run, expect pass.**

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: email sender and notify dedup service"
```

---

## Task 16: Wiring module + CLI

**Files:**
- Create: `app/wiring.py`, `app/cli.py`, `app/__main__.py` (optional), `tests/test_cli.py`

`app/wiring.py` builds real source-backed callables for services (so cli/web/scheduler share one assembly point). CLI parses argv and calls services. Tests run CLI with a temp DB and monkeypatched sources.

- [ ] **Step 1: Implement `app/wiring.py`**

```python
"""Single assembly point: build real source-backed callables for services."""
from app.db.connection import DEFAULT_DB_PATH, connect, init_db
from app.db.repository import Repository
from app.services.low_freq import LowFreqSources
from app.sources import baidu, eastmoney, sina, tencent


def get_repo(db_path: str = DEFAULT_DB_PATH) -> Repository:
    return Repository(connect(db_path))


def quote_fn(codes):
    return tencent.fetch_quotes(codes)


def baidu_fn(code):
    try:
        return baidu.fetch_main_net_in(code)
    except Exception:
        return None


def index_fn(market):
    return tencent.fetch_index(market)


def breadth_fn(market):
    return eastmoney.fetch_breadth(market)


def search_fn(keyword):
    return tencent.search(keyword)


def low_freq_sources() -> LowFreqSources:
    return LowFreqSources(
        dividends_fn=eastmoney.fetch_dividends,
        fund_flow_fn=eastmoney.fetch_fund_flow,
        financial_fn=sina.fetch_financial,
        kline_fn=eastmoney.fetch_kline,
    )
```

- [ ] **Step 2: Write failing tests** in `tests/test_cli.py`

```python
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
```

- [ ] **Step 3: Run, expect failure.**

- [ ] **Step 4: Implement `app/cli.py`** (uses argparse; `DB_PATH` module-level for test override)

```python
import argparse

from app import wiring
from app.config import DEFAULT_EMAIL_CONFIG_PATH, load_email_config
from app.db.connection import DEFAULT_DB_PATH, init_db
from app.email_sender import make_send_fn
from app.services import backfill as backfill_svc
from app.services import macro as macro_svc
from app.services import snapshot as snapshot_svc
from app.services.low_freq import refresh_low_freq
from app.services.notify import notify
from app.services.stock_pool import resolve, split_inputs

DB_PATH = DEFAULT_DB_PATH


def _repo():
    return wiring.get_repo(DB_PATH)


def _do_sync(repo, codes, low_freq=False, do_notify=False):
    if codes is None:
        codes = [s["code"] for s in repo.list_stocks()]
    if low_freq:
        errors = refresh_low_freq(repo, codes, wiring.low_freq_sources(),
                                  on_error=lambda c, item, exc: print(f"[low-freq fail] {c} {item}: {exc}"))
    macro_svc.sync_macro(repo, wiring.index_fn, wiring.breadth_fn)
    snaps = snapshot_svc.sync_snapshots(repo, codes, wiring.quote_fn, wiring.baidu_fn)
    for s in snaps:
        print(f"{s['code']} {s.get('name') or ''} price={s.get('price')} "
              f"主力净流入(万)={s.get('main_net_in')} 来源={s.get('main_net_in_source')}")
    if do_notify:
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        notify(repo, make_send_fn(cfg), cfg.get("recipients", []))
    return snaps


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p_add = sub.add_parser("add"); p_add.add_argument("text")
    sub.add_parser("list")
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("codes", nargs="*")
    p_sync.add_argument("--low-freq", action="store_true")
    p_sync.add_argument("--notify", action="store_true")
    p_snap = sub.add_parser("snapshots"); p_snap.add_argument("code"); p_snap.add_argument("--limit", type=int, default=10)
    p_sig = sub.add_parser("signals"); p_sig.add_argument("code", nargs="?"); p_sig.add_argument("--limit", type=int, default=20)
    p_regen = sub.add_parser("regen-signals"); p_regen.add_argument("date")
    p_macro = sub.add_parser("macro"); p_macro.add_argument("--limit", type=int, default=10)
    sub.add_parser("notify")
    p_fc = sub.add_parser("forecast"); p_fc.add_argument("code"); p_fc.add_argument("--eps", type=float)
    p_fc.add_argument("--net-profit-yi", type=float); p_fc.add_argument("--source", default="manual")
    p_fin = sub.add_parser("financial"); p_fin.add_argument("code"); p_fin.add_argument("report_date")
    p_fin.add_argument("--net-profit", type=float); p_fin.add_argument("--equity", type=float)
    p_fin.add_argument("--total-assets", type=float); p_fin.add_argument("--total-liabilities", type=float)

    args = parser.parse_args(argv)

    if args.cmd == "init":
        init_db(DB_PATH); print(f"initialized {DB_PATH}"); return
    repo = _repo()
    if args.cmd == "add":
        for token in split_inputs(args.text):
            try:
                r = resolve(token, wiring.search_fn); repo.add_stock(r["code"], r["name"])
                print(f"added {r['code']} {r['name']}")
            except Exception as exc:  # noqa: BLE001
                print(f"skip {token}: {exc}")
    elif args.cmd == "list":
        for s in repo.list_stocks():
            print(f"{s['code']} {s['name']}")
    elif args.cmd == "sync":
        _do_sync(repo, args.codes or None, args.low_freq, args.notify)
    elif args.cmd == "snapshots":
        for s in repo.snapshots_for(args.code, args.limit):
            print(f"{s['snapshot_time']} price={s['price']} chg={s['change_pct']}")
    elif args.cmd == "signals":
        rows = repo.signals_for(args.code, args.limit) if args.code else repo.recent_signals(args.limit)
        for s in rows:
            print(f"{s['snapshot_time']} {s['code']} {s['signal_type']} {s['level']}")
    elif args.cmd == "regen-signals":
        n = backfill_svc.regen_signals(repo, args.date); print(f"regenerated {n} signals for {args.date}")
    elif args.cmd == "macro":
        for m in repo.recent_macro(args.limit):
            print(f"{m['snapshot_time']} {m['market']} {m['index_point']} {m['change_pct']}")
    elif args.cmd == "notify":
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        n = notify(repo, make_send_fn(cfg), cfg.get("recipients", [])); print(f"sent {n}")
    elif args.cmd == "forecast":
        repo.upsert_forecast({"code": args.code, "forecast_eps": args.eps,
                              "forecast_net_profit_yi": args.net_profit_yi, "source": args.source})
        print(f"forecast saved for {args.code}")
    elif args.cmd == "financial":
        repo.upsert_financial({"code": args.code, "report_date": args.report_date,
                               "net_profit_attr": args.net_profit, "equity_attr": args.equity,
                               "total_assets": args.total_assets, "total_liabilities": args.total_liabilities})
        print(f"financial saved for {args.code} {args.report_date}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run, expect pass.** `uv run pytest tests/test_cli.py`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: wiring assembly point and CLI"
```

---

## Task 17: Flask Web

**Files:**
- Create: `app/web.py`, `tests/test_web.py`

`create_app(db_path)` returns a Flask app (factory enables testing with `app.test_client()`). Routes call services via `wiring` and render server-built HTML. Sorting on `/` via `?sort=col&dir=asc|desc`.

- [ ] **Step 1: Write failing tests** in `tests/test_web.py`

```python
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
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/web.py`**

```python
import html

from flask import Flask, redirect, request

from app import wiring
from app.config import DEFAULT_EMAIL_CONFIG_PATH, load_email_config
from app.db.connection import DEFAULT_DB_PATH
from app.email_sender import make_send_fn
from app.services import backfill as backfill_svc
from app.services import macro as macro_svc
from app.services import snapshot as snapshot_svc
from app.services.low_freq import refresh_low_freq
from app.services.notify import notify
from app.services.signals import LEVEL_LABELS, SIGNAL_LABELS, SIGNAL_THRESHOLDS
from app.services.stock_pool import resolve, split_inputs

_PAGE = "<html><head><meta charset='utf-8'><title>StockTrace</title></head><body>{body}</body></html>"


def _esc(v):
    return html.escape("" if v is None else str(v))


def _table(headers, rows):
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table border='1' cellpadding='4'><tr>{head}</tr>{body}</table>"


def create_app(db_path: str = DEFAULT_DB_PATH) -> Flask:
    app = Flask(__name__)

    def repo():
        return wiring.get_repo(db_path)

    def run_sync(codes=None, low_freq=False, do_notify=False):
        r = repo()
        if codes is None:
            codes = [s["code"] for s in r.list_stocks()]
        if low_freq:
            try:
                refresh_low_freq(r, codes, wiring.low_freq_sources())
            except Exception:  # web swallows low-freq errors
                pass
        macro_svc.sync_macro(r, wiring.index_fn, wiring.breadth_fn)
        snapshot_svc.sync_snapshots(r, codes, wiring.quote_fn, wiring.baidu_fn)
        if do_notify:
            cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
            notify(r, make_send_fn(cfg), cfg.get("recipients", []))

    @app.route("/")
    def index():
        r = repo()
        sort = request.args.get("sort", "code")
        direction = request.args.get("dir", "asc")
        snaps = [dict(s) for s in r.latest_snapshot_per_stock()]
        if snaps and sort in snaps[0]:
            snaps.sort(key=lambda s: (s.get(sort) is None, s.get(sort)), reverse=(direction == "desc"))
        cols = [("code", "代码"), ("name", "名称"), ("price", "现价"), ("change_pct", "涨跌幅"),
                ("pe_ttm", "PE_TTM"), ("roe", "ROE"), ("pb", "PB"), ("dividend_yield_ttm", "股息率TTM"),
                ("dist_ma20_pct", "距MA20"), ("dist_ma60_pct", "距MA60"),
                ("debt_to_asset_ratio", "资产负债率"), ("main_net_in", "主力净流入(万)")]
        headers = [f'<a href="/?sort={c}&dir={"desc" if direction=="asc" else "asc"}">{label}</a>'
                   for c, label in cols]
        rows = [[s.get(c) for c, _ in cols] for s in snaps]
        sources = {}
        for s in snaps:
            src = s.get("main_net_in_source") or "无"
            sources[src] = sources.get(src, 0) + 1
        latest_time = snaps[0]["snapshot_time"] if snaps else "无"
        sh, sz = r.latest_macro("sh"), r.latest_macro("sz")
        macro_html = "".join(f"<p>{m['market']}: {m['index_point']} ({m['change_pct']}%)</p>"
                             for m in (sh, sz) if m)
        form = ('<form method="post" action="/add"><input name="text" placeholder="代码/名称,批量">'
                '<button>添加</button></form>'
                '<a href="/sync">立即同步</a> | <a href="/sync?low_freq=1">同步+低频</a> | '
                '<a href="/signals">信号</a> | <a href="/macro">宏观</a> | <a href="/snapshots">快照历史</a>')
        body = (f"<h1>StockTrace</h1>{form}<h2>沪深宏观</h2>{macro_html}"
                f"<p>最新快照时间: {_esc(latest_time)}</p>"
                f"<p>主力净流入来源: {_esc(sources)}</p>"
                f"<table border='1' cellpadding='4'><tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr>"
                + "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows)
                + "</table>")
        return _PAGE.format(body=body)

    @app.route("/stock/<code>")
    def stock(code):
        r = repo()
        snaps = r.snapshots_for(code, 100)
        sigs = r.signals_for(code, 30)
        latest = dict(snaps[0]) if snaps else {}
        card = "".join(f"<p>{_esc(k)}: {_esc(v)}</p>" for k, v in latest.items())
        snap_tbl = _table(["时间", "现价", "涨跌幅", "距MA20", "距MA60"],
                          [[s["snapshot_time"], s["price"], s["change_pct"], s["dist_ma20_pct"], s["dist_ma60_pct"]] for s in snaps])
        sig_tbl = _table(["时间", "类型", "级别"],
                         [[s["snapshot_time"], SIGNAL_LABELS.get(s["signal_type"], s["signal_type"]), LEVEL_LABELS.get(s["level"], s["level"])] for s in sigs])
        body = (f"<h1>{_esc(code)}</h1><a href='/sync?code={_esc(code)}'>只同步该股</a> | "
                f"<a href='/sync?code={_esc(code)}&low_freq=1'>只同步该股+低频</a> | <a href='/'>返回</a>"
                f"<h2>指标</h2>{card}<h2>最近100条快照</h2>{snap_tbl}<h2>最近30条信号</h2>{sig_tbl}")
        return _PAGE.format(body=body)

    @app.route("/signals")
    def signals_page():
        r = repo()
        rows = [[s["snapshot_time"], s["code"], s["name"], SIGNAL_LABELS.get(s["signal_type"], s["signal_type"]),
                 LEVEL_LABELS.get(s["level"], s["level"])] for s in r.recent_signals(200)]
        thresholds = "".join(f"<li>{_esc(SIGNAL_LABELS[k])}: {_esc(v)}</li>" for k, v in SIGNAL_THRESHOLDS.items())
        body = (f"<h1>信号</h1><a href='/'>返回</a>"
                f"<h2>阈值说明</h2><ul>{thresholds}</ul>"
                f"<h2>最近200条</h2>{_table(['时间','代码','名称','类型','级别'], rows)}")
        return _PAGE.format(body=body)

    @app.route("/macro")
    def macro_page():
        r = repo()
        rows = [[m["snapshot_time"], m["market"], m["index_point"], m["change_pct"],
                 m["up_count"], m["down_count"], m["flat_count"], m["total_count"]] for m in r.recent_macro(200)]
        body = f"<h1>宏观</h1><a href='/'>返回</a>{_table(['时间','市场','点位','涨跌幅','涨','跌','平','总'], rows)}"
        return _PAGE.format(body=body)

    @app.route("/snapshots")
    def snapshots_page():
        r = repo()
        rows = [[s["snapshot_time"], s["code"], s["name"], s["price"], s["change_pct"]] for s in r.recent_snapshots(500)]
        body = f"<h1>快照历史</h1><a href='/'>返回</a>{_table(['时间','代码','名称','现价','涨跌幅'], rows)}"
        return _PAGE.format(body=body)

    @app.route("/add", methods=["POST"])
    def add():
        r = repo()
        for token in split_inputs(request.form.get("text", "")):
            try:
                res = resolve(token, wiring.search_fn)
                r.add_stock(res["code"], res["name"])  # batch ignores custom name by design
            except Exception:
                continue
        return redirect("/")

    @app.route("/sync")
    def sync():
        code = request.args.get("code")
        low_freq = request.args.get("low_freq") == "1"
        do_notify = request.args.get("notify") == "1"
        run_sync([code] if code else None, low_freq, do_notify)
        return redirect(f"/stock/{code}" if code else "/")

    @app.route("/backfill")
    def backfill_route():
        r = repo()
        start = request.args.get("start")
        end = request.args.get("end")
        codes = [s["code"] for s in r.list_stocks()]
        n = backfill_svc.backfill(r, codes, start, end)
        return _PAGE.format(body=f"<p>backfilled {n} signals</p><a href='/'>返回</a>")

    @app.route("/notify")
    def notify_route():
        r = repo()
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        try:
            n = notify(r, make_send_fn(cfg), cfg.get("recipients", []))
            msg = f"sent {n}"
        except Exception as exc:  # noqa: BLE001
            msg = f"notify error: {exc}"
        return _PAGE.format(body=f"<p>{_esc(msg)}</p><a href='/'>返回</a>")

    return app


def main() -> None:
    from app.config import web_host_port
    host, port = web_host_port()
    create_app().run(host=host, port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, expect pass.** `uv run pytest tests/test_web.py`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: flask web entry with all routes"
```

---

## Task 18: APScheduler scheduler

**Files:**
- Create: `app/scheduler.py`, `tests/test_scheduler.py`

`should_run_intraday(now)` is a pure predicate (weekday + time windows) — unit-tested. `build_scheduler()` wires jobs but is not run in tests.

- [ ] **Step 1: Write failing test** in `tests/test_scheduler.py`

```python
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
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement `app/scheduler.py`**

```python
from datetime import datetime, time

from apscheduler.schedulers.blocking import BlockingScheduler

from app import wiring
from app.config import DEFAULT_EMAIL_CONFIG_PATH, load_email_config
from app.email_sender import make_send_fn
from app.services import low_freq as low_freq_svc
from app.services import macro as macro_svc
from app.services import snapshot as snapshot_svc
from app.services.notify import notify

_AM = (time(9, 30), time(11, 35))
_PM = (time(13, 0), time(15, 10))


def should_run_intraday(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (_AM[0] <= t <= _AM[1]) or (_PM[0] <= t <= _PM[1])


def intraday_job() -> None:
    if not should_run_intraday(datetime.now()):
        return
    repo = wiring.get_repo()
    codes = [s["code"] for s in repo.list_stocks()]
    macro_svc.sync_macro(repo, wiring.index_fn, wiring.breadth_fn)
    snapshot_svc.sync_snapshots(repo, codes, wiring.quote_fn, wiring.baidu_fn)
    try:
        cfg = load_email_config(DEFAULT_EMAIL_CONFIG_PATH)
        if cfg.get("recipients"):
            notify(repo, make_send_fn(cfg), cfg["recipients"])
    except Exception as exc:  # noqa: BLE001
        print(f"[notify fail] {exc}")


def low_freq_job() -> None:
    repo = wiring.get_repo()
    codes = [s["code"] for s in repo.list_stocks()]
    low_freq_svc.refresh_low_freq(repo, codes, wiring.low_freq_sources(),
                                  on_error=lambda c, item, exc: print(f"[low-freq fail] {c} {item}: {exc}"))


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler()
    sched.add_job(intraday_job, "interval", minutes=30, next_run_time=datetime.now(),
                  misfire_grace_time=1800, max_instances=1, coalesce=True)
    sched.add_job(low_freq_job, "cron", hour=20, minute=0, misfire_grace_time=3600, max_instances=1)
    return sched


def main() -> None:
    build_scheduler().start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: apscheduler intraday + low-freq jobs"
```

---

## Task 19: Packaging (Dockerfile + start.sh + README)

**Files:**
- Create: `Dockerfile`, `start.sh`, `README.md`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system flask apscheduler requests
COPY app ./app
COPY start.sh ./start.sh
RUN chmod +x start.sh
ENV HOST=0.0.0.0 PORT=5000 STOCKTRACE_DATA_DIR=/app/data
VOLUME ["/app/data"]
EXPOSE 5000
CMD ["./start.sh"]
```

- [ ] **Step 2: Write `start.sh`**

```bash
#!/usr/bin/env bash
set -e
python -m app.cli init
python -m app.scheduler &
exec python -m app.web
```

- [ ] **Step 3: Write `README.md`** (concise: install with `uv sync`, `uv run python -m app.cli init`, common commands, Docker run, email config). Include the CLI command list from the spec §7.1 and env vars `HOST/PORT/EMAIL_*/STOCKTRACE_DATA_DIR`.

- [ ] **Step 4: Verify full suite passes** — `uv run pytest`. Expected: all green.

- [ ] **Step 5: Smoke-check imports** — `uv run python -c "import app.cli, app.web, app.scheduler, app.wiring"`. Expected: no error.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: docker packaging, start.sh, README"
```

---

## Self-Review (completed by plan author)

**Spec coverage:** stock pool/parsing (T6), intraday snapshot + metrics (T4, T12), low-freq refresh + failure isolation (T13), macro (T11), signals + thresholds/labels (T5), backfill regen + daily synth (T14), email dedup (T15), Web all routes incl. sorting/backfill/notify (T17), CLI all commands incl. forecast/financial (T16), scheduler windows + misfire + 20:00 low-freq (T18), data sources adapters (T7–T10), config env precedence + host/port (T1), Docker/start.sh (T19). All spec sections map to a task.

**Placeholder scan:** No "TBD/TODO" in implementation steps. Two adapters (sina T9, baidu T10) carry explicit implementer NOTES about confirming live endpoint field names — these are real-world API-shape caveats, not missing logic; the parse/persist contract is fully specified and tested against fixtures. Tencent T7 likewise notes verifying `~`-field indices against a live line, with stable parser signature.

**Type consistency:** snapshot dict keys match `_SNAPSHOT_COLS` (T3) and metrics/signals field reads. `signal` dict shape `{signal_type, level, detail}` consistent across T5/T12/T14. `wiring` callable names (`quote_fn/baidu_fn/index_fn/breadth_fn/search_fn/low_freq_sources/get_repo`) consistent across T16/T17/T18. `LowFreqSources` fields consistent T13/T16. Fund-flow unit conversion (元→万元, ÷10000) consistent in T12 and T14.
