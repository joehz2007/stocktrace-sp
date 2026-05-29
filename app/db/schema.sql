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
