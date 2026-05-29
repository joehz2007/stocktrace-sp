from app.services.signals import generate_signals, SIGNAL_LABELS, LEVEL_LABELS


def snap(**kw):
    base = {"snapshot_time": "2026-05-29 10:30:00", "change_pct": 0.0, "volume_ratio": 1.0,
            "main_net_in": 0.0, "amount_wan": 1000.0, "dividend_yield_ttm": 0.0,
            "dist_ma20_pct": 0.0, "dist_ma60_pct": 0.0, "ma20": 100.0, "ma60": 100.0, "price": 100.0}
    base.update(kw)
    return base


def test_first_snapshot_is_baseline_only():
    assert generate_signals(None, snap(volume_ratio=3.0, change_pct=5.0)) == []


def test_volume_surge_up_after_10am():
    prev = snap()
    curr = snap(snapshot_time="2026-05-29 10:30:00", volume_ratio=2.0, change_pct=2.0)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_up" in types


def test_volume_surge_up_suppressed_before_10am():
    prev = snap(snapshot_time="2026-05-29 09:30:00")
    curr = snap(snapshot_time="2026-05-29 09:45:00", volume_ratio=3.0, change_pct=5.0)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_up" not in types


def test_volume_surge_up_not_repeated_when_prev_already_true():
    prev = snap(volume_ratio=2.0, change_pct=2.0)
    curr = snap(volume_ratio=2.1, change_pct=2.5)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_up" not in types  # ordinary state: only on rising edge


def test_volume_surge_down():
    prev = snap()
    curr = snap(volume_ratio=2.5, change_pct=-2.0)
    types = [s["signal_type"] for s in generate_signals(prev, curr)]
    assert "volume_surge_down" in types


def test_main_inflow_and_outflow():
    prev = snap()
    inflow = snap(main_net_in=90.0, amount_wan=1000.0)  # 9% >= 8%
    assert "main_inflow" in [s["signal_type"] for s in generate_signals(prev, inflow)]
    outflow = snap(main_net_in=-90.0, amount_wan=1000.0)
    assert "main_outflow" in [s["signal_type"] for s in generate_signals(prev, outflow)]


def test_high_dividend_healthy_vs_broken():
    prev = snap()
    healthy = snap(dividend_yield_ttm=5.0, dist_ma60_pct=2.0)
    assert "high_dividend_healthy" in [s["signal_type"] for s in generate_signals(prev, healthy)]
    broken = snap(dividend_yield_ttm=5.0, dist_ma60_pct=-2.0)
    assert "high_dividend_broken" in [s["signal_type"] for s in generate_signals(prev, broken)]


def test_golden_cross_and_death_cross():
    prev = snap(ma20=99.0, ma60=100.0)   # diff <= 0
    curr = snap(ma20=101.0, ma60=100.0)  # diff > 0
    assert "golden_cross" in [s["signal_type"] for s in generate_signals(prev, curr)]
    prev2 = snap(ma20=101.0, ma60=100.0)  # diff >= 0
    curr2 = snap(ma20=99.0, ma60=100.0)   # diff < 0
    assert "death_cross" in [s["signal_type"] for s in generate_signals(prev2, curr2)]


def test_cross_above_below_ma60():
    prev = snap(dist_ma60_pct=0.5)
    curr = snap(dist_ma60_pct=1.5)
    assert "above_ma60" in [s["signal_type"] for s in generate_signals(prev, curr)]
    prev2 = snap(dist_ma60_pct=-0.5)
    curr2 = snap(dist_ma60_pct=-1.5)
    assert "below_ma60" in [s["signal_type"] for s in generate_signals(prev2, curr2)]


def test_bias_overheat_oversold():
    prev = snap(dist_ma20_pct=14.0)
    curr = snap(dist_ma20_pct=16.0)
    assert "bias_overheat" in [s["signal_type"] for s in generate_signals(prev, curr)]
    prev2 = snap(dist_ma20_pct=-14.0)
    curr2 = snap(dist_ma20_pct=-16.0)
    assert "bias_oversold" in [s["signal_type"] for s in generate_signals(prev2, curr2)]


def test_labels_exist_for_all_types():
    for t in ["volume_surge_up", "volume_surge_down", "main_inflow", "main_outflow",
              "high_dividend_healthy", "high_dividend_broken", "golden_cross", "death_cross",
              "above_ma60", "below_ma60", "bias_overheat", "bias_oversold"]:
        assert t in SIGNAL_LABELS
    assert set(LEVEL_LABELS) == {"low", "mid", "high"}
