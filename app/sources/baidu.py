"""Baidu 股市通 minute-level fund-flow adapter.

Endpoint + headers follow the proven (zero-auth) pattern from the a-stock-data
skill. Baidu serves this without a cookie/token from a China/residential IP, but
blocks some datacenter/overseas IPs at the edge (HTTP 403). When unreachable or
empty this returns None and the snapshot logic falls back to local daily
fund_flow (by design).
"""
import datetime

from app.sources.base import http_get_json

_BAIDU_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0",
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}


def parse_main_net_in(payload: dict):
    """Latest cumulative main-force net inflow in 万元, or None.

    Result.update_data is ';'-separated minute rows; each row is comma-separated
    with mainForce at index 2 (per a-stock-data). ResultCode may be int 0 or
    string "0", so compare as str. Result is a dict on success, [] on rejection.
    """
    if str(payload.get("ResultCode", -1)) != "0":
        return None
    result = payload.get("Result")
    raw = result.get("update_data", "") if isinstance(result, dict) else ""
    if not raw:
        return None
    last = None
    for seg in raw.split(";"):
        parts = seg.split(",")
        if len(parts) >= 9 and parts[2] not in ("", "-"):
            last = parts[2]
    if last is None:
        return None
    try:
        return float(last)
    except ValueError:
        return None


def fetch_main_net_in(code: str, date: str | None = None):
    date = date or datetime.date.today().strftime("%Y%m%d")  # Baidu wants YYYYMMDD
    payload = http_get_json(
        "https://finance.pae.baidu.com/vapi/v1/fundflow",
        params={"code": code, "market": "ab", "date": date, "finClientType": "pc"},
        headers=_BAIDU_HEADERS,
    )
    return parse_main_net_in(payload)
