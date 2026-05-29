"""Maintainer tool: verify Eastmoney endpoints against live data.

Run: uv run python scripts/verify_eastmoney.py [code]

Checks kline / fund flow / dividends / market breadth: prints a raw sample and
what each parser extracted, so the field mappings in app/sources/eastmoney.py
can be confirmed against the live JSON shape.
"""
import sys

from app.sources import eastmoney as em
from app.sources.base import http_get_json


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"

    print("=== KLINE (last 2 rows) ===")
    raw = http_get_json("https://push2his.eastmoney.com/api/qt/stock/kline/get",
                        params={"secid": em._secid(code), "fields1": "f1",
                                "fields2": "f51,f52,f53,f54,f55,f56,f57",
                                "klt": "101", "fqt": "1", "end": "20500101", "lmt": "2"})
    print("raw klines:", raw.get("data", {}).get("klines"))
    print("parsed:", em.parse_kline(raw)[-2:])

    print("\n=== FUND FLOW (last 2 rows) ===")
    raw = http_get_json("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                        params={"secid": em._secid(code), "fields1": "f1",
                                "fields2": "f51,f52,f53,f54,f55,f56", "lmt": "2"})
    print("raw klines:", raw.get("data", {}).get("klines"))
    print("parsed:", em.parse_fund_flow(raw)[-2:])

    print("\n=== DIVIDENDS (latest 2) ===")
    divs = em.fetch_dividends(code)
    for d in divs[:2]:
        print(" ", d)

    print("\n=== MARKET BREADTH (sh) ===")
    print("parsed:", em.fetch_breadth("sh"))


if __name__ == "__main__":
    main()
