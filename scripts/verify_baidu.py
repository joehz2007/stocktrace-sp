"""Maintainer tool: verify Baidu minute fund-flow against live data.

Run: uv run python scripts/verify_baidu.py [code]

Uses the zero-auth gushitong endpoint from a-stock-data. NOTE: Baidu blocks some
datacenter/overseas IPs at the edge (HTTP 403); from a China/residential IP this
returns real minute data. On rejection the adapter returns None and the snapshot
falls back to local daily fund_flow (by design).
"""
import datetime
import sys

import requests

from app.sources.baidu import _BAIDU_HEADERS, fetch_main_net_in, parse_main_net_in


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    date = datetime.date.today().strftime("%Y%m%d")
    r = requests.get("https://finance.pae.baidu.com/vapi/v1/fundflow",
                     params={"code": code, "market": "ab", "date": date, "finClientType": "pc"},
                     headers=_BAIDU_HEADERS, timeout=10)
    print(f"HTTP {r.status_code}, body len {len(r.text)}")
    if r.status_code != 200 or not r.text:
        print("-> edge-blocked (likely IP/geo). Snapshot falls back to local fund_flow.")
        return
    payload = r.json()
    print("ResultCode:", payload.get("ResultCode"))
    ud = (payload.get("Result") or {}).get("update_data", "") if isinstance(payload.get("Result"), dict) else ""
    print("minute segments:", len(ud.split(";")) if ud else 0)
    print("parse_main_net_in (万):", parse_main_net_in(payload))
    print("fetch_main_net_in (万):", fetch_main_net_in(code))


if __name__ == "__main__":
    main()
