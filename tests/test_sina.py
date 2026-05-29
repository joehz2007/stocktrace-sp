import json
import os

from app.sources.sina import parse_financial

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_parse_financial():
    raw = json.load(open(os.path.join(_FIX, "sina_balance.json"), encoding="utf-8"))
    fin = parse_financial(raw)
    assert fin["report_date"] == "2025-12-31"
    assert fin["total_assets"] == 3.0e11
    assert fin["total_liabilities"] == 1.0e11
    assert fin["equity_attr"] == 2.0e11
    assert fin["net_profit_attr"] == 8.0e10
