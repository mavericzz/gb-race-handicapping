"""Join Punters + Racing & Sports, then score each race for a WIN overlay."""

from __future__ import annotations

from src.handicap.model import PastRun, RunnerInput, handicap_race
from src.scrapers.parsers import horse_key, venue_key


def _index_meetings(blob: dict) -> dict[tuple[str, int], dict]:
    out = {}
    for meeting in blob.get("meetings") or []:
        vk = venue_key(meeting.get("venue") or meeting.get("venue_slug") or "")
        for race in meeting.get("races") or []:
            num = race.get("race_number")
            if num is None:
                continue
            out[(vk, int(num))] = {**race, "venue": meeting.get("venue"), "venue_slug": meeting.get("venue_slug")}
    return out


def _best_last_run(punter: dict, rs: dict | None) -> PastRun:
    last = dict(punter.get("last_run") or {})
    if rs:
        past = rs.get("past_runs") or []
        if past:
            first = past[0]
            last.setdefault("track", first.get("track"))
            last.setdefault("date", first.get("date"))
            if not last.get("weight_kg") and first.get("weight_kg"):
                last["weight_kg"] = first.get("weight_kg")
            if last.get("finish") is None:
                last["finish"] = first.get("finish")
            if last.get("distance_m") is None:
                last["distance_m"] = first.get("distance_m")
            if last.get("beaten_lengths") is None and first.get("beaten_lengths") is not None:
                last["beaten_lengths"] = first.get("beaten_lengths")
            last.setdefault("going", first.get("going"))
    sects = punter.get("sectionals") or []
    latest = sects[0] if sects else {}
    fsp = None
    par = None
    l400 = None
    if latest:
        # finishing speed proxy: late vs average when Punters supplies speeds
        late = latest.get("late_speed")
        avg = latest.get("l400_speed") or latest.get("late_speed")
        if late and avg:
            fsp = float(late)
            par = float(avg)
        l400 = latest.get("l400_split")
        last.setdefault("going", latest.get("track_condition"))
        last.setdefault("early_speed", latest.get("early_speed"))
        last.setdefault("late_speed", latest.get("late_speed"))
    return PastRun(
        finish=last.get("finish"),
        beaten_lengths=last.get("beaten_lengths"),
        distance_m=last.get("distance_m"),
        weight_kg=last.get("weight_kg"),
        going=last.get("going"),
        class_code=last.get("class_code"),
        track=last.get("track"),
        time_s=last.get("time_s"),
        fsp=fsp,
        par_fsp=par,
        l400_s=float(l400) if l400 not in (None, "") else None,
        early_speed=last.get("early_speed"),
        late_speed=last.get("late_speed"),
    )


def merge_and_score(punters: dict, racing_sports: dict) -> dict:
    p_idx = _index_meetings(punters)
    r_idx = _index_meetings(racing_sports)
    keys = sorted(set(p_idx) | set(r_idx))
    meetings: dict[str, dict] = {}

    for venue_key, race_no in keys:
        p_race = p_idx.get((venue_key, race_no), {})
        r_race = r_idx.get((venue_key, race_no), {})
        venue = p_race.get("venue") or r_race.get("venue") or venue_key
        p_runners = {horse_key(r.get("name") or ""): r for r in p_race.get("runners") or []}
        r_runners = {horse_key(r.get("name") or ""): r for r in r_race.get("runners") or []}
        names = list(dict.fromkeys([*p_runners, *r_runners]))
        going = p_race.get("going") or r_race.get("going")
        distance_m = p_race.get("distance_m") or r_race.get("distance_m")
        if not distance_m:
            past_d = [
                (run.get("past_runs") or [{}])[0].get("distance_m")
                for run in (r_race.get("runners") or [])
            ]
            past_d = [d for d in past_d if d]
            distance_m = sorted(past_d)[len(past_d) // 2] if past_d else 1207
        field_size = max(len(names), 2)
        inputs: list[RunnerInput] = []
        detail = []
        for key in names:
            p = p_runners.get(key) or {}
            r = r_runners.get(key) or {}
            name = p.get("name") or r.get("name") or key
            runner = RunnerInput(
                name=name,
                number=p.get("number") or r.get("number"),
                barrier=p.get("barrier") or r.get("barrier"),
                today_weight_kg=p.get("weight_kg") or r.get("weight_kg"),
                handicap_rating=p.get("handicap_rating"),
                market_odds=p.get("odds"),
                last_run=_best_last_run(p, r),
                going=going,
                distance_m=float(distance_m),
                field_size=field_size,
                scratched=bool(p.get("scratched")),
            )
            inputs.append(runner)
            detail.append({
                "punters": p,
                "racing_sports": r,
                "last_run": runner.last_run.__dict__,
            })
        scored = handicap_race(inputs, venue=venue)
        by_name = {row["name"]: row for row in scored}
        combined = []
        for runner, meta in zip(inputs, detail):
            row = by_name.get(runner.name) or {}
            combined.append({**row, **meta, "name": runner.name})
        combined.sort(key=lambda r: r.get("rank") or 99)
        meeting = meetings.setdefault(venue, {
            "venue": venue,
            "date": punters.get("date") or racing_sports.get("date"),
            "races": [],
        })
        plays = [r for r in combined if r.get("action") == "PLAY"]
        meeting["races"].append({
            "race_number": race_no,
            "name": p_race.get("name") or r_race.get("name") or f"Race {race_no}",
            "going": going,
            "distance_m": distance_m,
            "url_punters": p_race.get("url"),
            "url_rs": r_race.get("url"),
            "off_time": p_race.get("off_time") or r_race.get("off_time"),
            "plays": plays,
            "runners": combined,
        })

    card = {
        "date": punters.get("date") or racing_sports.get("date"),
        "objective": "win overlay",
        "meetings": list(meetings.values()),
    }
    card["plays"] = [
        {**play, "venue": m["venue"], "race_number": race["race_number"], "race_name": race["name"]}
        for m in card["meetings"]
        for race in m["races"]
        for play in race["plays"]
    ]
    return card
