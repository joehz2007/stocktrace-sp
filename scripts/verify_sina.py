"""Maintainer tool: verify Sina financial-statement parsing against live data.

Run: uv run python scripts/verify_sina.py [code]

Sina serves the statements as GBK tab-separated downloads. This prints the raw
head, the detected report-date header, every row label (so you can confirm the
exact label strings used in app/sources/sina.py), and what fetch_financial
extracts. (See the "NOTE for maintainer" in app/sources/sina.py.)
"""
import sys

from app.sources.base import http_get
from app.sources.sina import (
    _BALANCE_URL, _INCOME_URL, _parse_sina_csv, fetch_financial,
)


def _dump(name: str, url: str) -> None:
    print(f"\n=== {name}: {url} ===")
    text = http_get(url, encoding="gbk")
    print("--- raw head (300 chars) ---")
    print(text[:300])
    dates, items = _parse_sina_csv(text)
    print(f"--- report dates (header), {len(dates)} cols ---")
    print(dates[:6])
    print(f"--- {len(items)} row labels (first 40) ---")
    for label in list(items)[:40]:
        print(f"  {label!r}")


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    _dump("BalanceSheet", _BALANCE_URL.format(code=code))
    _dump("ProfitStatement", _INCOME_URL.format(code=code))
    print("\n=== fetch_financial() extracted ===")
    for k, v in fetch_financial(code).items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
