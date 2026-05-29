"""Maintainer tool: verify Baidu minute-level fund-flow parsing against live data.

Run: uv run python scripts/verify_baidu.py [code]

Baidu 股市通 endpoints often require cookies / a signed token, so a bare request
may be rejected or return an empty payload — in which case the snapshot logic
falls back to local daily fund flow (by design). This prints the raw payload
keys and what parse_main_net_in extracts, to confirm/repair the accessor in
app/sources/baidu.py against the live JSON shape.
"""
import json
import sys

from app.sources.baidu import fetch_main_net_in, parse_main_net_in
from app.sources.base import http_get_json


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    try:
        raw = http_get_json("https://finance.pae.baidu.com/selfselect/getstockquotation",
                            params={"code": code, "all": "1", "isIndex": "false", "finClientType": "pc"})
    except Exception as exc:  # noqa: BLE001
        print(f"request failed: {type(exc).__name__}: {str(exc)[:120]}")
        print("-> snapshot falls back to local daily fund_flow (by design).")
        return
    print("=== top-level keys ===", list(raw)[:10])
    print("=== Result keys ===", list(raw.get("Result", {}))[:20] if isinstance(raw.get("Result"), dict) else type(raw.get("Result")))
    print("=== raw sample (400 chars) ===")
    print(json.dumps(raw, ensure_ascii=False)[:400])
    print("=== parse_main_net_in ===", parse_main_net_in(raw))
    print("=== fetch_main_net_in ===", fetch_main_net_in(code))


if __name__ == "__main__":
    main()
