import json
import os

from app.sources.sina import normalize_report_date, parse_financial

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_parse_financial():
    raw = json.load(open(os.path.join(_FIX, "sina_balance.json"), encoding="utf-8"))
    fin = parse_financial(raw)
    assert fin["report_date"] == "2025-12-31"
    assert fin["total_assets"] == 3.0e11
    assert fin["total_liabilities"] == 1.0e11
    assert fin["equity_attr"] == 2.0e11
    assert fin["net_profit_attr"] == 8.0e10


def test_normalize_report_date():
    # Sina YYYYMMDD -> YYYY-MM-DD so metrics._report_month reads the month correctly
    assert normalize_report_date("20260331") == "2026-03-31"
    assert normalize_report_date("2025-12-31") == "2025-12-31"  # already dashed, unchanged
    assert normalize_report_date(None) is None


def test_parse_financial_normalizes_date():
    fin = parse_financial({"report_date": "20251231", "total_assets": 1.0})
    assert fin["report_date"] == "2025-12-31"
