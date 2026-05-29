"""Pure indicator calculations. No IO. Return None when inputs are insufficient."""
from datetime import date, timedelta
from datetime import datetime


def moving_average(closes: list[float], window: int) -> float | None:
    if len(closes) < window or window <= 0:
        return None
    return sum(closes[-window:]) / window


def distance_pct(price: float | None, ma: float | None) -> float | None:
    if price is None or not ma:
        return None
    return (price - ma) / ma * 100


def trend_status(price, ma20, ma60) -> str | None:
    if price is None or ma20 is None or ma60 is None:
        return None
    if price > ma20 and ma20 > ma60:
        return "多头：价高于MA20，MA20高于MA60"
    if price < ma20 and ma20 < ma60:
        return "空头：价低于MA20，MA20低于MA60"
    if price > ma60:
        return "中性偏强：价高于MA60"
    return "中性偏弱：价低于MA60"


def roe(net_profit_attr, equity_attr, report_month: int) -> float | None:
    if not equity_attr:
        return None
    factor = {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}.get(report_month)
    if factor is None:
        return None
    return net_profit_attr * factor / equity_attr * 100


def debt_to_asset_ratio(total_liabilities, total_assets) -> float | None:
    if not total_assets:
        return None
    return total_liabilities / total_assets * 100


def dynamic_pe(price, forecast_eps, market_cap_yi, forecast_net_profit_yi):
    if forecast_eps:
        return price / forecast_eps, "eps"
    if market_cap_yi and forecast_net_profit_yi:
        return market_cap_yi / forecast_net_profit_yi, "net_profit"
    return None, None


def _latest_per_report_period(dividends: list[dict]) -> dict[str, dict]:
    """Keep the dividend with the latest announce_date per report_date."""
    best: dict[str, dict] = {}
    for d in dividends:
        rd = d["report_date"]
        cur = best.get(rd)
        if cur is None or (d.get("announce_date") or "") > (cur.get("announce_date") or ""):
            best[rd] = d
    return best


def dividend_yield_ttm(dividends: list[dict], total_shares: float, market_cap: float,
                       as_of: str | None = None) -> float | None:
    """近一年报告期(含预案)现金分红总额 / 最近总市值 ×100%.

    pretax_bonus_per10 是每10股税前派息,先换算为每股 (/10)。
    口径:只统计"近一年报告期"——以数据中最近一个报告期(report_date,不晚于 as_of)
    为锚,纳入其往前 365 天内(不含整一年前那期)的所有报告期(年度+中期,含预案),
    避免把多年分红累加导致虚高;锚定最近报告期而非今天,可避开年初新年报未披露时的
    "空窗"。as_of 默认今天,用于排除晚于快照日的未来报告期。
    """
    if not market_cap:
        return None
    upper = as_of or date.today().strftime("%Y-%m-%d")
    per_period = _latest_per_report_period(dividends)
    valid = {rd: d for rd, d in per_period.items() if rd and rd <= upper}
    if not valid:
        return 0.0
    latest = max(valid)
    cutoff = (datetime.strptime(latest, "%Y-%m-%d").date() - timedelta(days=365)).strftime("%Y-%m-%d")
    total_cash = 0.0
    for rd, d in valid.items():
        if rd <= cutoff:  # strictly within one year of the latest report period
            continue
        per10 = d.get("pretax_bonus_per10")
        if per10 is None:
            continue
        total_cash += (per10 / 10.0) * total_shares
    return total_cash / market_cap * 100
