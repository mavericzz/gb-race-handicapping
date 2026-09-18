"""Win overlay handicapper: figures → probabilities → Kelly stakes."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.handicap.sectionals import (
    early_speed_score,
    late_split_upgrade_lbs,
    sectional_upgrade_lbs,
    softmax,
)
from src.handicap.weights import kg_to_lbs, performance_figure


@dataclass
class PastRun:
    finish: int | None = None
    beaten_lengths: float | None = None
    distance_m: float | None = None
    weight_kg: float | None = None
    going: str | None = None
    class_code: str | None = None
    track: str | None = None
    time_s: float | None = None
    fsp: float | None = None
    par_fsp: float | None = None
    l400_s: float | None = None
    early_speed: float | None = None
    late_speed: float | None = None
    field_l400_s: float | None = None


@dataclass
class RunnerInput:
    name: str
    number: int | None = None
    barrier: int | None = None
    today_weight_kg: float | None = None
    handicap_rating: float | None = None
    official_or: float | None = None
    market_odds: float | None = None
    last_run: PastRun | None = None
    extra_runs: list[PastRun] = field(default_factory=list)
    going: str | None = None
    distance_m: float = 1207
    field_size: int = 12
    rs_rating: float | None = None
    scratched: bool = False


DRAW_BIAS = {
    # (venue_slug, max_furlongs): (low_draw_bonus_lbs, high_draw_bonus_lbs)
    ("chester", 8): (3.0, -2.5),
    ("ayr", 6.5): (0.0, 1.5),  # big-field 6f often stands' rail
    ("newmarket", 8): (0.5, 0.5),
    ("newcastle", 6.5): (-0.5, 1.0),
}


def _draw_bias_lbs(venue: str, distance_m: float, barrier: int | None, field_size: int) -> float:
    if not barrier or field_size < 8:
        return 0.0
    f = distance_m / 201.168
    key = None
    venue_l = (venue or "").lower()
    for (track, max_f), bias in DRAW_BIAS.items():
        if track in venue_l and f <= max_f:
            key = bias
            break
    if not key:
        return 0.0
    low, high = key
    tertile = (barrier - 1) / max(1, field_size - 1)
    if tertile <= 0.33:
        return low
    if tertile >= 0.67:
        return high
    return 0.0


def _going_fit(today: str | None, last: str | None) -> float:
    if not today or not last:
        return 0.0
    t, l = today.lower(), last.lower()
    softish = ("soft", "heavy", "yielding", "good to soft", "g/s")
    today_soft = any(s in t for s in softish)
    last_soft = any(s in l for s in softish)
    if today_soft and last_soft:
        return 1.5
    if today_soft and not last_soft:
        return -1.0
    return 0.0


def runner_figure(runner: RunnerInput, venue: str = "") -> dict:
    rating = runner.official_or or runner.handicap_rating or runner.rs_rating or 80.0
    last = runner.last_run or PastRun()
    beaten = last.beaten_lengths if last.beaten_lengths is not None else 0.0
    last_dist = last.distance_m or runner.distance_m
    today_lbs = kg_to_lbs(runner.today_weight_kg) if runner.today_weight_kg else 126.0
    last_lbs = kg_to_lbs(last.weight_kg) if last.weight_kg else today_lbs

    fig = performance_figure(
        last_or=rating,
        beaten_lengths=beaten if last.finish and last.finish > 1 else 0.0,
        distance_m=last_dist,
        last_carried_lbs=last_lbs,
        today_lbs=today_lbs,
    )
    if last.finish == 1:
        fig += 1.0

    sect = 0.0
    if last.fsp is not None and last.par_fsp is not None:
        sect += sectional_upgrade_lbs(last.fsp, last.par_fsp)
    sect += late_split_upgrade_lbs(last.l400_s, last.field_l400_s, last_dist)

    draw = _draw_bias_lbs(venue, runner.distance_m, runner.barrier, runner.field_size)
    going = _going_fit(runner.going, last.going)
    pace = early_speed_score(last.early_speed, last.late_speed)
    # 5-6f: on-pace is an asset; 10f+: closing is an asset
    f = runner.distance_m / 201.168
    pace_lbs = (0.4 * pace) if f <= 6.5 else (-0.25 * pace)

    if runner.rs_rating is not None and runner.handicap_rating is not None:
        fig += 0.25 * (runner.rs_rating - runner.handicap_rating)

    total = fig + sect + draw + going + pace_lbs
    return {
        "name": runner.name,
        "figure": round(total, 2),
        "base": round(fig, 2),
        "sectional": round(sect, 2),
        "draw": round(draw, 2),
        "going": round(going, 2),
        "pace": round(pace_lbs, 2),
        "weight_swing": round(last_lbs - today_lbs, 2),
        "beaten_lengths": beaten,
    }


def decimal_implied_prob(odds: float | None) -> float | None:
    if odds is None or odds <= 1.0:
        return None
    return 1.0 / odds


def fractional_kelly(edge: float, decimal_odds: float, fraction: float = 0.25) -> float:
    """Quarter-Kelly stake as a fraction of bankroll. 0 if no edge."""
    b = decimal_odds - 1.0
    if b <= 0 or edge <= 0:
        return 0.0
    # edge here is (p_model / p_market - 1); convert to p*b - q
    p_market = 1.0 / decimal_odds
    p = p_market * (1.0 + edge)
    q = 1.0 - p
    full = (p * b - q) / b
    return max(0.0, min(0.05, full * fraction))


def handicap_race(
    runners: list[RunnerInput],
    venue: str = "",
    temperature: float | None = None,
    min_edge: float = 0.12,
) -> list[dict]:
    live = [r for r in runners if not r.scratched]
    if not live:
        return []
    if temperature is None:
        temperature = 4.0 + 0.22 * max(0, len(live) - 8)
    figs = [runner_figure(r, venue=venue) for r in live]
    scores = [f["figure"] for f in figs]
    probs = softmax(scores, temperature=temperature)
    out = []
    for runner, fig, p_model in zip(live, figs, probs):
        p_mkt = decimal_implied_prob(runner.market_odds)
        edge = None
        stake = 0.0
        if p_mkt and runner.market_odds:
            edge = p_model / p_mkt - 1.0
            if edge >= min_edge and p_model >= 0.06:
                stake = fractional_kelly(edge, runner.market_odds)
        action = "PASS"
        rated = runner.official_or is not None or runner.handicap_rating is not None or runner.rs_rating is not None
        odds = runner.market_odds
        playable = (
            stake > 0
            and rated
            and odds is not None
            and 2.2 <= odds <= 21.0
            and p_model >= 0.08
        )
        if playable:
            action = "PLAY"
        elif edge is not None and edge > 0.05:
            action = "WATCH"
        row = {
            **fig,
            "number": runner.number,
            "barrier": runner.barrier,
            "weight_kg": runner.today_weight_kg,
            "rating": runner.official_or or runner.handicap_rating,
            "rs_rating": runner.rs_rating,
            "odds": runner.market_odds,
            "p_model": round(p_model, 4),
            "p_market": round(p_mkt, 4) if p_mkt else None,
            "edge": round(edge, 3) if edge is not None else None,
            "stake_pct": round(stake * 100, 2),
            "action": action,
        }
        out.append(row)
    out.sort(key=lambda r: r["figure"], reverse=True)
    for i, row in enumerate(out, 1):
        row["rank"] = i
    plays = [r for r in out if r["action"] == "PLAY"]
    if len(plays) > 1:
        best = max(plays, key=lambda r: (r.get("edge") or 0, r.get("figure") or 0))
        for row in out:
            if row["action"] == "PLAY" and row["name"] != best["name"]:
                row["action"] = "WATCH"
                row["stake_pct"] = 0.0
    return out
