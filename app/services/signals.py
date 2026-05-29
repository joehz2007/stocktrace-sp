"""Event-diff signal generation. Pure. prev=None means baseline only."""
from datetime import datetime

SIGNAL_LABELS = {
    "volume_surge_up": "放量上涨", "volume_surge_down": "放量下跌",
    "main_inflow": "主力净流入", "main_outflow": "主力净流出",
    "high_dividend_healthy": "高股息（健康）", "high_dividend_broken": "高股息（破位）",
    "golden_cross": "金叉", "death_cross": "死叉",
    "above_ma60": "站上MA60", "below_ma60": "跌破MA60",
    "bias_overheat": "乖离过热", "bias_oversold": "乖离超卖",
}
LEVEL_LABELS = {"low": "低", "mid": "中", "high": "高"}

# threshold descriptions shown on /signals
SIGNAL_THRESHOLDS = {
    "volume_surge_up": "10:00后，量比≥2.0 且涨幅≥+2%",
    "volume_surge_down": "10:00后，量比≥2.5 且跌幅≤-2%",
    "main_inflow": "10:00后，主力净额/成交额≥+8%",
    "main_outflow": "10:00后，主力净额/成交额≤-8%",
    "high_dividend_healthy": "股息率≥5% 且未跌破MA60",
    "high_dividend_broken": "股息率≥5% 且跌破MA60",
    "golden_cross": "MA20-MA60 由≤0 变 >0",
    "death_cross": "MA20-MA60 由≥0 变 <0",
    "above_ma60": "距MA60 由<+1% 升到≥+1%",
    "below_ma60": "距MA60 由>-1% 跌到≤-1%",
    "bias_overheat": "距MA20 由<+15% 升到≥+15%",
    "bias_oversold": "距MA20 由>-15% 跌到≤-15%",
}


def _after_10am(snapshot_time: str) -> bool:
    t = datetime.strptime(snapshot_time, "%Y-%m-%d %H:%M:%S")
    return (t.hour, t.minute) >= (10, 0)


def _g(snap, key, default=0.0):
    v = snap.get(key) if isinstance(snap, dict) else snap[key]
    return default if v is None else v


def _main_ratio(snap) -> float:
    amt = _g(snap, "amount_wan", 0.0)
    if not amt:
        return 0.0
    return _g(snap, "main_net_in", 0.0) / amt * 100


def _ordinary(prev, curr, predicate) -> bool:
    """Fire only when curr satisfies predicate and prev did not."""
    return predicate(curr) and not predicate(prev)


def generate_signals(prev, curr) -> list[dict]:
    if prev is None:
        return []
    out: list[dict] = []
    after10 = _after_10am(curr["snapshot_time"])

    def add(stype, level):
        out.append({"signal_type": stype, "level": level, "detail": SIGNAL_THRESHOLDS[stype]})

    # ordinary states (rising edge), gated by 10:00 for the volume/main signals
    if after10:
        if _ordinary(prev, curr, lambda s: _g(s, "volume_ratio") >= 2.0 and _g(s, "change_pct") >= 2.0):
            add("volume_surge_up", "mid")
        if _ordinary(prev, curr, lambda s: _g(s, "volume_ratio") >= 2.5 and _g(s, "change_pct") <= -2.0):
            add("volume_surge_down", "high")
        if _ordinary(prev, curr, lambda s: _main_ratio(s) >= 8.0):
            add("main_inflow", "low")
        if _ordinary(prev, curr, lambda s: _main_ratio(s) <= -8.0):
            add("main_outflow", "low")

    if _ordinary(prev, curr, lambda s: _g(s, "dividend_yield_ttm") >= 5.0 and _g(s, "dist_ma60_pct") >= 0):
        add("high_dividend_healthy", "low")
    if _ordinary(prev, curr, lambda s: _g(s, "dividend_yield_ttm") >= 5.0 and _g(s, "dist_ma60_pct") < 0):
        add("high_dividend_broken", "mid")

    # crossing states (compare both sides)
    pd = _g(prev, "ma20") - _g(prev, "ma60")
    cd = _g(curr, "ma20") - _g(curr, "ma60")
    if pd <= 0 and cd > 0:
        add("golden_cross", "high")
    if pd >= 0 and cd < 0:
        add("death_cross", "high")

    if _g(prev, "dist_ma60_pct") < 1.0 and _g(curr, "dist_ma60_pct") >= 1.0:
        add("above_ma60", "mid")
    if _g(prev, "dist_ma60_pct") > -1.0 and _g(curr, "dist_ma60_pct") <= -1.0:
        add("below_ma60", "high")

    if _g(prev, "dist_ma20_pct") < 15.0 and _g(curr, "dist_ma20_pct") >= 15.0:
        add("bias_overheat", "mid")
    if _g(prev, "dist_ma20_pct") > -15.0 and _g(curr, "dist_ma20_pct") <= -15.0:
        add("bias_oversold", "mid")

    return out
