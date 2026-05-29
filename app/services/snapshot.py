from datetime import datetime

from app.services import metrics, signals


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _report_month(report_date: str) -> int:
    return int(report_date[5:7])


def _build_snapshot(repo, code: str, quote: dict, baidu_fn, ts: str) -> dict:
    price = quote.get("price")
    di = repo.latest_daily_indicator(code)
    ma20 = di["ma20"] if di else None
    ma60 = di["ma60"] if di else None
    fin = repo.latest_financial(code)
    fc = repo.get_forecast(code)

    # main net inflow: prefer baidu (万元), fall back to local daily fund flow (元 -> 万元)
    main_net_in, source = baidu_fn(code), "baidu"
    if main_net_in is None:
        ff = repo.latest_fund_flow(code)
        if ff is not None:
            main_net_in, source = ff["main_net_in"] / 10000.0, "fund_flow"
        else:
            main_net_in, source = None, None

    roe = debt = div_yield = None
    if fin:
        roe = metrics.roe(fin["net_profit_attr"], fin["equity_attr"], _report_month(fin["report_date"]))
        debt = metrics.debt_to_asset_ratio(fin["total_liabilities"], fin["total_assets"])
    market_cap_yi = quote.get("market_cap_yi")
    if market_cap_yi:
        dividends = [dict(d) for d in repo.dividends_for(code)]
        total_shares = market_cap_yi * 1e8 / price if price else 0
        div_yield = metrics.dividend_yield_ttm(dividends, total_shares, market_cap_yi * 1e8,
                                               as_of=ts[:10])

    pe_dyn, pe_dyn_src = metrics.dynamic_pe(
        price, fc["forecast_eps"] if fc else None, market_cap_yi,
        fc["forecast_net_profit_yi"] if fc else None)

    return {
        "code": code, "name": quote.get("name"), "snapshot_time": ts,
        "price": price, "change_pct": quote.get("change_pct"), "turnover_pct": quote.get("turnover_pct"),
        "amount_wan": quote.get("amount_wan"), "volume_ratio": quote.get("volume_ratio"),
        "pe_static": quote.get("pe_static"), "pe_ttm": quote.get("pe_ttm"),
        "pe_dynamic": pe_dyn, "pe_dynamic_source": pe_dyn_src, "pb": quote.get("pb"),
        "market_cap_yi": market_cap_yi, "float_market_cap_yi": quote.get("float_market_cap_yi"),
        "dividend_yield_ttm": div_yield, "roe": roe, "ma20": ma20, "ma60": ma60,
        "dist_ma20_pct": metrics.distance_pct(price, ma20),
        "dist_ma60_pct": metrics.distance_pct(price, ma60),
        "trend_status": metrics.trend_status(price, ma20, ma60),
        "debt_to_asset_ratio": debt, "main_net_in": main_net_in, "main_net_in_source": source,
    }


def sync_snapshots(repo, codes, quote_fn, baidu_fn, now_fn=_now) -> list[dict]:
    ts = now_fn()
    quotes = quote_fn(codes) or {}
    persisted = []
    for code in codes:
        quote = quotes.get(code)
        if not quote:
            continue
        snap = _build_snapshot(repo, code, quote, baidu_fn, ts)
        repo.insert_snapshot(snap)
        _generate_for(repo, code, snap)
        persisted.append(snap)
    return persisted


def _generate_for(repo, code: str, curr: dict) -> None:
    last_two = repo.last_two_snapshots(code)
    prev = dict(last_two[1]) if len(last_two) >= 2 else None
    for sig in signals.generate_signals(prev, curr):
        repo.insert_signal({"code": code, "name": curr.get("name"),
                            "signal_type": sig["signal_type"], "level": sig["level"],
                            "snapshot_time": curr["snapshot_time"], "detail": sig["detail"]})
