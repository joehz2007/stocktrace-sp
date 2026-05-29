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
        return self.conn.execute("SELECT * FROM stock ORDER BY added_at, code").fetchall()

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
