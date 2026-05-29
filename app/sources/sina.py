"""Sina financial-statement adapter.

The persisted contract is fixed: parse_financial(mapped_dict) ->
{report_date, net_profit_attr, equity_attr, total_assets, total_liabilities}.

NOTE for maintainer: Sina's statement endpoints return CSV/semi-structured data,
not clean JSON. fetch_financial retrieves the balance sheet + income statement and
maps the relevant rows into the dict shape consumed by parse_financial. Confirm the
exact endpoint columns with one real request and adjust the mapping in
_map_balance_sheet / _map_income only — keep parse_financial's output keys stable so
low_freq and metrics are unaffected. financial can also be populated manually via
`python -m app.cli financial`.
"""
import csv
import io

from app.sources.base import http_get

_KEYS = ["report_date", "net_profit_attr", "equity_attr", "total_assets", "total_liabilities"]

_BALANCE_URL = ("https://money.finance.sina.com.cn/corp/go.php/vDOWN_BalanceSheet/"
                "displaytype/4/stockid/{code}/ctrl/all.phtml")
_INCOME_URL = ("https://money.finance.sina.com.cn/corp/go.php/vDOWN_ProfitStatement/"
               "displaytype/4/stockid/{code}/ctrl/all.phtml")


def parse_financial(payload: dict) -> dict:
    """Normalize a decoded financial payload into the fields we persist."""
    return {k: payload.get(k) for k in _KEYS}


def _parse_sina_csv(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """Sina CSV: tab-separated, first row = report dates, each later row a line item."""
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    rows = [r for r in reader if r]
    if not rows:
        return [], {}
    header = rows[0][1:]  # first cell is the row label
    items: dict[str, list[str]] = {}
    for r in rows[1:]:
        if r:
            items[r[0].strip()] = r[1:]
    return header, items


def _num(items: dict, label: str, idx: int):
    vals = items.get(label)
    if not vals or idx >= len(vals):
        return None
    try:
        return float(vals[idx])
    except (ValueError, TypeError):
        return None


def fetch_financial(code: str) -> dict:
    balance_text = http_get(_BALANCE_URL.format(code=code), encoding="gbk")
    income_text = http_get(_INCOME_URL.format(code=code), encoding="gbk")
    dates, bal = _parse_sina_csv(balance_text)
    _, inc = _parse_sina_csv(income_text)
    if not dates:
        return parse_financial({})
    mapped = {
        "report_date": dates[0],
        "total_assets": _num(bal, "资产总计", 0),
        "total_liabilities": _num(bal, "负债合计", 0),
        "equity_attr": _num(bal, "归属于母公司股东权益合计", 0),
        "net_profit_attr": _num(inc, "归属于母公司所有者的净利润", 0),
    }
    return parse_financial(mapped)
