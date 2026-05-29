"""Eastmoney adapter.

Endpoints/params and the multi-URL fallback follow the proven patterns from the
sibling `stocktrace` project, which runs these reliably: try several host/scheme
combinations (push2 / push2his, http / https) because flaky proxies and edge
nodes drop specific combinations intermittently. A `Referer` header is required
by some endpoints. Parsers stay pure and are fixture-tested.
"""
from app.sources.base import http_get_json

_HEADERS = {"Referer": "https://quote.eastmoney.com/"}


def _secid(code: str) -> str:
    return f"{'1' if code[0] in ('6', '9') else '0'}.{code}"


def _first_ok(urls: list[str], params: dict, *, require_klines=False):
    """Try each URL until one returns usable JSON; raise the last error if all fail."""
    last_exc = None
    for url in urls:
        try:
            payload = http_get_json(url, params=params, headers=_HEADERS)
        except Exception as exc:  # noqa: BLE001 - try the next host/scheme
            last_exc = exc
            continue
        if require_klines and not (payload.get("data") or {}).get("klines"):
            continue  # reachable but empty — try the next combination
        return payload
    if last_exc:
        raise last_exc
    return {}


def parse_kline(payload: dict) -> list[dict]:
    rows = []
    for line in (payload.get("data") or {}).get("klines", []):
        f = line.split(",")
        rows.append({"trade_date": f[0], "open": float(f[1]), "close": float(f[2]),
                     "high": float(f[3]), "low": float(f[4]),
                     "volume": float(f[5]), "amount": float(f[6])})
    return rows


def parse_fund_flow(payload: dict) -> list[dict]:
    rows = []
    for line in (payload.get("data") or {}).get("klines", []):
        f = line.split(",")
        rows.append({"trade_date": f[0], "main_net_in": float(f[1]) if f[1] != "-" else 0.0})
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
    """ulist.np/get returns {"data": {"diff": [{f104, f105, f106}]}}."""
    diff = (payload.get("data") or {}).get("diff") or []
    d = diff[0] if diff else {}
    up, down, flat = d.get("f104"), d.get("f105"), d.get("f106")
    if not all(isinstance(x, int) for x in (up, down, flat)):
        return {"up_count": None, "down_count": None, "flat_count": None, "total_count": None}
    return {"up_count": up, "down_count": down, "flat_count": flat, "total_count": up + down + flat}


def fetch_kline(code: str, limit: int = 120) -> list[dict]:
    params = {"secid": _secid(code), "fields1": "f1,f2,f3,f4,f5,f6",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
              "klt": "101", "fqt": "1", "end": "20500101", "lmt": str(limit)}
    payload = _first_ok([
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        "http://push2his.eastmoney.com/api/qt/stock/kline/get",
    ], params, require_klines=True)
    return parse_kline(payload)


def fetch_fund_flow(code: str, limit: int = 120) -> list[dict]:
    params = {"secid": _secid(code), "fields1": "f1,f2,f3,f7",
              "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
              "klt": "101", "lmt": str(limit)}
    payload = _first_ok([
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        "http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get",
        "http://push2.eastmoney.com/api/qt/stock/fflow/kline/get",
    ], params, require_klines=True)
    return parse_fund_flow(payload)


def fetch_dividends(code: str) -> list[dict]:
    payload = http_get_json(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={"reportName": "RPT_SHAREBONUS_DET", "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")', "pageNumber": "1", "pageSize": "50",
                "sortColumns": "NOTICE_DATE", "sortTypes": "-1", "source": "WEB", "client": "WEB"},
        headers=_HEADERS,
    )
    return parse_dividends(payload)


def fetch_breadth(market: str) -> dict:
    secids = "1.000001" if market == "sh" else "0.399001"
    payload = _first_ok([
        "https://push2.eastmoney.com/api/qt/ulist.np/get",
        "http://push2.eastmoney.com/api/qt/ulist.np/get",
    ], {"fltt": "2", "invt": "2", "secids": secids, "fields": "f104,f105,f106"})
    return parse_breadth(payload)
