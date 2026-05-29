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
