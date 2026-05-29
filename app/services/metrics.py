"""Pure indicator calculations. No IO. Return None when inputs are insufficient."""


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


def dividend_yield_ttm(dividends: list[dict], total_shares: float, market_cap: float) -> float | None:
    """近一年报告期(含预案)现金分红总额 / 最近总市值 ×100%.
    pretax_bonus_per10 是每10股税前派息,先换算为每股 (/10)。
    """
    if not market_cap:
        return None
    per_period = _latest_per_report_period(dividends)
    total_cash = 0.0
    for d in per_period.values():
        per10 = d.get("pretax_bonus_per10")
        if per10 is None:
            continue
        per_share = per10 / 10.0
        total_cash += per_share * total_shares
    return total_cash / market_cap * 100
