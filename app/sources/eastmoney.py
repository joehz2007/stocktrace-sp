from app.sources.base import http_get_json


def _secid(code: str) -> str:
    return f"{'1' if code[0] in ('6', '9') else '0'}.{code}"


def parse_kline(payload: dict) -> list[dict]:
    rows = []
    for line in payload.get("data", {}).get("klines", []):
        f = line.split(",")
        rows.append({"trade_date": f[0], "open": float(f[1]), "close": float(f[2]),
                     "high": float(f[3]), "low": float(f[4]),
                     "volume": float(f[5]), "amount": float(f[6])})
    return rows


def parse_fund_flow(payload: dict) -> list[dict]:
    rows = []
    for line in payload.get("data", {}).get("klines", []):
        f = line.split(",")
        rows.append({"trade_date": f[0], "main_net_in": float(f[1])})
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
    d = payload.get("data", {})
    up, down, flat = d.get("f104", 0), d.get("f105", 0), d.get("f106", 0)
    return {"up_count": up, "down_count": down, "flat_count": flat,
            "total_count": (up or 0) + (down or 0) + (flat or 0)}


def fetch_kline(code: str, limit: int = 120) -> list[dict]:
    payload = http_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={"secid": _secid(code), "fields1": "f1", "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": "101", "fqt": "1", "end": "20500101", "lmt": str(limit)},
    )
    return parse_kline(payload)


def fetch_fund_flow(code: str, limit: int = 120) -> list[dict]:
    payload = http_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
        params={"secid": _secid(code), "fields1": "f1", "fields2": "f51,f52,f53,f54,f55,f56", "lmt": str(limit)},
    )
    return parse_fund_flow(payload)


def fetch_dividends(code: str) -> list[dict]:
    payload = http_get_json(
        "https://datacenter-web.eastmoney.com/api/data/v1/get",
        params={"reportName": "RPT_SHAREBONUS_DET", "columns": "ALL",
                "filter": f'(SECURITY_CODE="{code}")', "pageSize": "50"},
    )
    return parse_dividends(payload)


def fetch_breadth(market: str) -> dict:
    secid = "1.000001" if market == "sh" else "0.399001"
    payload = http_get_json("https://push2.eastmoney.com/api/qt/stock/get",
                            params={"secid": secid, "fields": "f104,f105,f106"})
    return parse_breadth(payload)
