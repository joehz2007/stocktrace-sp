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
    # real smartbox format: market~code~name~pinyin~type, results joined by ^,
    # name as \uXXXX unicode escapes (贵州茅台 / 五粮液)
    raw = r'v_hint="sh~600519~贵州茅台~gzmt~GP-A^sz~000858~五粮液~wly~GP-A";'
    hits = parse_search(raw)
    assert hits[0] == {"code": "600519", "name": "贵州茅台"}
    assert hits[1]["code"] == "000858"
    assert hits[1]["name"] == "五粮液"


def test_parse_search_empty():
    assert parse_search('v_hint="";') == []
