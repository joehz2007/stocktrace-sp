"""Tencent quote/search/index adapter.

Field indices in parse_quote were verified against live data (sh600519) via
scripts/verify_tencent.py: price[3], change_pct[32], amount_wan[37] (万元),
turnover_pct[38], pe_ttm[39], float_market_cap_yi[44], market_cap_yi[45] (亿元),
pb[46], volume_ratio[49], pe_static[53]. Re-run that script if the format changes.
"""
import re
import urllib.parse

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
    """smartbox 返回 v_hint="市场~代码~名称~拼音~类型^...";
    多个结果用 ^ 分隔,名称是 \\uXXXX unicode 转义。"""
    text = raw.strip()
    if '="' in text:
        text = text.split('="', 1)[1].rsplit('"', 1)[0]
    if not text:
        return []
    text = urllib.parse.unquote(text)
    if "\\u" in text:  # smartbox escapes names as \uXXXX; only decode when present
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
    hits = []
    for item in text.split("^"):
        parts = item.split("~")
        if len(parts) < 3:
            continue
        market, code, name = parts[0].lower(), parts[1], parts[2]
        if market in ("sh", "sz", "bj") and code.isdigit() and len(code) == 6:
            hits.append({"code": code, "name": name})
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
