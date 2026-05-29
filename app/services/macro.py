from datetime import datetime


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sync_macro(repo, index_fn, breadth_fn, now_fn=_now) -> None:
    ts = now_fn()
    for market in ("sh", "sz"):
        idx = index_fn(market) or {}
        breadth = breadth_fn(market) or {}
        repo.insert_macro({"market": market, "snapshot_time": ts,
                           "index_point": idx.get("index_point"),
                           "change_point": idx.get("change_point"),
                           "change_pct": idx.get("change_pct"),
                           "high": idx.get("high"), "low": idx.get("low"),
                           "amount": idx.get("amount"),
                           "up_count": breadth.get("up_count"),
                           "down_count": breadth.get("down_count"),
                           "flat_count": breadth.get("flat_count"),
                           "total_count": breadth.get("total_count")})
