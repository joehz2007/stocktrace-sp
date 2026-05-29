"""Maintainer tool: verify Tencent quote field indices against live data.

Run: uv run python scripts/verify_tencent.py [code]

Prints every '~'-separated field with its index, then what our parser extracted,
so you can confirm the positional indices in app/sources/tencent.py match the
live response. (See the "NOTE for maintainer" in the spec/plan.)
"""
import sys

from app.sources.base import http_get
from app.sources.tencent import _market, parse_quote

# index -> the snapshot field our parser maps it to
_MAPPED = {1: "name", 2: "code", 3: "price", 32: "change_pct", 37: "amount_wan",
           38: "turnover_pct", 39: "pe_ttm", 44: "float_market_cap_yi",
           45: "market_cap_yi", 46: "pb", 49: "volume_ratio", 53: "pe_static"}


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    raw = http_get(f"https://qt.gtimg.cn/q={_market(code)}{code}", encoding="gbk")
    print("=== raw response ===")
    print(raw.strip()[:400], "...\n")

    body = raw.split('"', 2)[1] if '"' in raw else ""
    fields = body.split("~")
    print(f"=== {len(fields)} fields (index: value) — ★ = read by our parser ===")
    for i, val in enumerate(fields[:60]):
        star = f"  ★ -> {_MAPPED[i]}" if i in _MAPPED else ""
        print(f"  [{i:>2}] {val!r}{star}")

    print("\n=== parse_quote() extracted ===")
    parsed = parse_quote(raw).get(code, {})
    for k, v in parsed.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
