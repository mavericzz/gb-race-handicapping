from src.handicap.sectionals import finishing_speed_pct, sectional_upgrade_lbs, softmax


def test_finishing_speed_pct_is_100_when_evenly_run():
    # 6f in 72s, last 2f in 24s → 100%
    assert round(finishing_speed_pct(24.0, 400.0, 72.0, 1200.0), 1) == 100.0


def test_sectional_upgrade_is_positive_when_horse_finishes_faster_than_par():
    assert sectional_upgrade_lbs(104.0, 100.0) > 0
    assert sectional_upgrade_lbs(96.0, 100.0) < 0


def test_softmax_puts_more_probability_on_the_highest_figure():
    probs = softmax([100.0, 97.0, 90.0], temperature=4.0)
    assert abs(sum(probs) - 1.0) < 1e-9
    assert probs[0] > probs[1] > probs[2]
