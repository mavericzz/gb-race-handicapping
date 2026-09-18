from __future__ import annotations

import math


def finishing_speed_pct(
    sectional_time_s: float,
    sectional_m: float,
    race_time_s: float,
    race_m: float,
) -> float:
    """Timeform-style finishing speed percentage."""
    if min(sectional_time_s, sectional_m, race_time_s, race_m) <= 0:
        raise ValueError("times and distances must be positive")
    return 100.0 * (sectional_m * race_time_s) / (sectional_time_s * race_m)


def sectional_upgrade_lbs(
    horse_fsp: float,
    par_fsp: float,
    *,
    lbs_per_fsp_point: float = 0.35,
    cap_lbs: float = 6.0,
) -> float:
    """
    Credit a horse that finished faster than par (held up in a slog or
    closed into a fast pace). Debit a horse that folded vs par.
    """
    raw = (float(horse_fsp) - float(par_fsp)) * lbs_per_fsp_point
    return max(-cap_lbs, min(cap_lbs, raw))


def late_split_upgrade_lbs(
    horse_l400_s: float | None,
    field_l400_s: float | None,
    distance_m: float,
) -> float:
    """Upgrade if the horse's last 400m was faster than the field median."""
    if horse_l400_s is None or field_l400_s is None:
        return 0.0
    if horse_l400_s <= 0 or field_l400_s <= 0:
        return 0.0
    delta_s = field_l400_s - horse_l400_s
    # ~0.2s ≈ 1 length at a sprint; convert via lbs/length at this trip.
    from src.handicap.weights import lbs_per_length

    lengths = delta_s / 0.2
    return max(-4.0, min(4.0, lengths * lbs_per_length(distance_m) * 0.35))


def early_speed_score(early_speed: float | None, late_speed: float | None) -> float:
    """Positive = on-pace; negative = come-from-behind. Used for 5-6f maps."""
    if early_speed is None:
        return 0.0
    late = late_speed if late_speed is not None else early_speed
    return float(early_speed) - float(late)


def softmax(xs: list[float], temperature: float = 4.0) -> list[float]:
    if not xs:
        return []
    t = max(0.4, float(temperature))
    shifted = [(x - max(xs)) / t for x in xs]
    exps = [math.exp(v) for v in shifted]
    total = sum(exps) or 1.0
    return [e / total for e in exps]
