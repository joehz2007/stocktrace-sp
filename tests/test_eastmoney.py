import json
import os

from app.sources.eastmoney import parse_kline, parse_fund_flow, parse_dividends, parse_breadth

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    return json.load(open(os.path.join(_FIX, name), encoding="utf-8"))


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
