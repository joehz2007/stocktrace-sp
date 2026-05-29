from datetime import datetime, timedelta

from app.services import metrics, signals


def _prev_trading_date(repo, code: str, date: str) -> str | None:
    rows = repo.daily_quotes(code)
    dates = [r["trade_date"] for r in rows if r["trade_date"] < date]
    return dates[-1] if dates else None


def synth_daily_snapshot(repo, code: str, date: str) -> dict | None:
    quotes = {r["trade_date"]: r for r in repo.daily_quotes(code)}
    q = quotes.get(date)
    if q is None:
        return None
    di = repo.daily_indicator_on_or_before(code, date)
    ma20 = di["ma20"] if di else None
    ma60 = di["ma60"] if di else None
    ff = repo.fund_flow_on_or_before(code, date)
    main = ff["main_net_in"] / 10000.0 if ff else None
    price = q["close"]
    stock = repo.get_stock(code)
    return {"code": code, "name": stock["name"] if stock else None,
            "snapshot_time": f"{date} 15:00:00", "price": price,
            "change_pct": 0.0, "amount_wan": (q["amount"] or 0) / 10000.0 if q["amount"] else 0.0,
            "volume_ratio": (di["vol_ratio_20"] if di else None) or 0.0,
            "ma20": ma20, "ma60": ma60,
            "dist_ma20_pct": metrics.distance_pct(price, ma20),
            "dist_ma60_pct": metrics.distance_pct(price, ma60),
            "trend_status": metrics.trend_status(price, ma20, ma60),
            "main_net_in": main, "main_net_in_source": "fund_flow" if ff else None,
            "dividend_yield_ttm": 0.0}


def regen_signals(repo, date: str, delete_first: bool = True) -> int:
    if delete_first:
        repo.delete_signals_on_date(date)
    count = 0
    for stock in repo.list_stocks():
        code = stock["code"]
        seq = [dict(s) for s in repo.snapshots_on_date(code, date)]
        prev = None
        for curr in seq:
            for sig in signals.generate_signals(prev, curr):
                repo.insert_signal({"code": code, "name": curr.get("name"),
                                    "signal_type": sig["signal_type"], "level": sig["level"],
                                    "snapshot_time": curr["snapshot_time"], "detail": sig["detail"]})
                count += 1
            prev = curr
    return count


def backfill(repo, codes, start: str | None, end: str | None) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    start = start or today
    end = end or start
    count = 0
    for code in codes:
        d = datetime.strptime(start, "%Y-%m-%d").date()
        last = datetime.strptime(end, "%Y-%m-%d").date()
        while d <= last:
            ds = d.strftime("%Y-%m-%d")
            curr = synth_daily_snapshot(repo, code, ds)
            if curr is not None:
                prev_date = _prev_trading_date(repo, code, ds)
                prev = synth_daily_snapshot(repo, code, prev_date) if prev_date else None
                for sig in signals.generate_signals(prev, curr):
                    repo.insert_signal({"code": code, "name": curr.get("name"),
                                        "signal_type": sig["signal_type"], "level": sig["level"],
                                        "snapshot_time": f"{ds} 15:00:00", "detail": sig["detail"]})
                    count += 1
            d += timedelta(days=1)
    return count
