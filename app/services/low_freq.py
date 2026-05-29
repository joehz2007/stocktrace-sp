from dataclasses import dataclass
from typing import Callable

from app.services import metrics


@dataclass
class LowFreqSources:
    dividends_fn: Callable[[str], list]
    fund_flow_fn: Callable[[str], list]
    financial_fn: Callable[[str], dict]
    kline_fn: Callable[[str], list]


def _compute_indicators(klines: list[dict]) -> list[dict]:
    closes = [k["close"] for k in klines]
    rows = []
    for i, k in enumerate(klines):
        window = closes[: i + 1]
        ma20 = metrics.moving_average(window, 20)
        ma60 = metrics.moving_average(window, 60)
        rows.append({"trade_date": k["trade_date"], "ma20": ma20, "ma60": ma60,
                     "vol_ratio_20": None,
                     "trend_status": metrics.trend_status(k["close"], ma20, ma60)})
    return rows


def refresh_low_freq(repo, codes, sources: LowFreqSources, on_error=None) -> list[tuple]:
    errors = []

    def run(code, item, fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - single item failure must not abort
            errors.append((code, item, exc))
            if on_error:
                on_error(code, item, exc)

    for code in codes:
        run(code, "dividends", lambda code=code: repo.replace_dividends(code, sources.dividends_fn(code)))
        run(code, "fund_flow", lambda code=code: repo.replace_fund_flows(code, sources.fund_flow_fn(code)))
        run(code, "financial", lambda code=code: repo.upsert_financial({**sources.financial_fn(code), "code": code}))

        def do_kline(code=code):
            klines = sources.kline_fn(code)
            repo.replace_daily_quotes(code, klines)
            repo.replace_daily_indicators(code, _compute_indicators(klines))
        run(code, "kline", do_kline)
    return errors
