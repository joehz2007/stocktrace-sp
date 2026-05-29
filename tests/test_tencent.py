import os

from app.sources.tencent import parse_quote, parse_search

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_parse_quote_basic():
    raw = open(os.path.join(_FIX, "tencent_quote.txt"), encoding="utf-8").read()
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
