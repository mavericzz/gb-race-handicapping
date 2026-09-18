"""Build Punters + Racing & Sports JSON, then score Saturday's WIN overlay."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scrapers.merge import merge_and_score
from src.scrapers.parsers import (
    horse_key,
    lbs_to_kg,
    parse_decimal_odds,
    parse_distance_m,
    parse_kg,
    parse_last_start_block,
    parse_st_lb,
    race_number_from_url,
)
from src.scrapers.racing_sports import VENUE_TITLES, _parse_past, furlongs_to_m

DATA = ROOT / "data"
LOGS = Path("/Users/toshasharma/.cursor/browser-logs")
PUNTERS_DUMPS = [
    LOGS / "cdp-response-Runtime.evaluate-2026-09-18T18-12-22-128Z.json",
    LOGS / "cdp-response-Runtime.evaluate-2026-09-18T18-13-12-097Z.json",
    LOGS / "cdp-response-Runtime.evaluate-2026-09-18T18-13-50-204Z.json",
    LOGS / "cdp-response-Runtime.evaluate-2026-09-18T18-14-23-858Z.json",
]
RS_MAIN = LOGS / "cdp-response-Runtime.evaluate-2026-09-18T18-22-36-202Z.json"
RS_NEWMARKET = LOGS / "cdp-response-Runtime.evaluate-2026-09-18T18-25-49-011Z.json"
VENUE_RE = re.compile(r"form-guide/horses/([a-z0-9-]+)-uk-")
VENUE_GOING = {
    "Ayr": "Soft",
    "Newbury": "Good",
    "Newmarket": "Good",
    "Wolverhampton": "Synthetic",
    "Newcastle": "Standard",
}


def _int(val) -> int | None:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _float(val) -> float | None:
    try:
        if val in ("", None):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _venue(url: str) -> str:
    m = VENUE_RE.search(url or "")
    return (m.group(1) if m else "unknown").replace("-", " ").title()


def build_punters(iso_date: str) -> dict:
    csvs = json.loads((DATA / f"punters_csvs_{iso_date}.json").read_text())
    races = []
    for path in PUNTERS_DUMPS:
        races.extend(json.loads(path.read_text())["result"]["value"])
    meetings: dict[str, dict] = {}
    for raw_race in races:
        url = raw_race.get("url") or ""
        venue = _venue(url)
        csv_url = next(
            (
                u if str(u).startswith("http") else "https://www.punters.com.au" + u
                for u in (raw_race.get("csv") or [])
                if u and "spreadsheet" in str(u)
            ),
            None,
        )
        csv_rows = {horse_key(r.get("Horse Name") or ""): r for r in csvs.get(csv_url or "", [])}
        going = raw_race.get("going") or VENUE_GOING.get(venue)
        distance_m = raw_race.get("distance_m")
        runners = []
        for raw in raw_race.get("runners") or []:
            name = raw.get("name") or ""
            row = csv_rows.get(horse_key(name)) or {}
            weight = raw.get("weight_kg") or parse_kg(raw.get("silk") or "")
            if weight is None:
                lbs = _float(row.get("Weight Carried") or row.get("Weight"))
                if lbs and lbs > 40:
                    weight = lbs_to_kg(lbs)
            last = parse_last_start_block(raw.get("detail_text") or "")
            last.setdefault("finish", _int(row.get("Last Start Finish Position")))
            if last.get("beaten_lengths") is None:
                last["beaten_lengths"] = _float(row.get("Last Start Margin"))
            last.setdefault("distance_m", parse_distance_m(row.get("Last Start Distance")))
            rating = _float(raw.get("rating")) or _float(row.get("Handicap Rating")) or None
            if rating == 0:
                rating = None
            runners.append({
                "name": name or row.get("Horse Name"),
                "key": horse_key(name or row.get("Horse Name") or ""),
                "number": _int(raw.get("number")) or _int(row.get("Num")),
                "barrier": _int(raw.get("barrier")) or _int(row.get("Barrier")),
                "jockey": raw.get("jockey") or row.get("Jockey"),
                "trainer": raw.get("trainer") or row.get("Trainer"),
                "weight_kg": weight,
                "handicap_rating": rating,
                "odds": parse_decimal_odds(raw.get("odds_text") or row.get("Best Fixed Odds")),
                "last_run": last,
                "source": "punters",
            })
        meeting = meetings.setdefault(venue, {
            "venue": venue,
            "venue_slug": venue.lower(),
            "date": iso_date,
            "races": [],
        })
        slug = Path(url.rstrip("/")).name.replace("-", " ")
        meeting["races"].append({
            "race_number": race_number_from_url(url),
            "name": slug,
            "url": url,
            "going": going,
            "distance_m": distance_m,
            "runners": runners,
        })
    return {"source": "punters", "date": iso_date, "meetings": list(meetings.values())}


def _rs_race(venue_slug: str, raw: dict) -> dict:
    off = re.match(r"(\d{2}:\d{2})", raw.get("name") or "")
    dists = []
    runners = []
    for item in raw.get("runners") or []:
        name = re.sub(r"\s+", " ", item.get("name") or "").strip()
        past = _parse_past(item.get("past") or [])
        dists.extend(p["distance_m"] for p in past if p.get("distance_m"))
        lbs = parse_st_lb(item.get("wgt"))
        runners.append({
            "name": name.title() if name.isupper() else name,
            "key": horse_key(name),
            "number": item.get("number"),
            "barrier": item.get("barrier"),
            "jockey": (item.get("jockey") or "").title(),
            "trainer": (item.get("trainer") or "").title(),
            "weight_kg": lbs_to_kg(lbs) if lbs else None,
            "weight_stlb": item.get("wgt"),
            "past_runs": past,
            "source": "racing_sports",
        })
    distance_m = furlongs_to_m(raw.get("distance_f")) if raw.get("distance_f") else None
    if not distance_m and dists:
        dists.sort()
        distance_m = dists[len(dists) // 2]
    return {
        "race_number": raw.get("race_number"),
        "name": raw.get("name") or f"{venue_slug} R{raw.get('race_number')}",
        "url": raw.get("url"),
        "going": raw.get("going") or VENUE_GOING.get(VENUE_TITLES.get(venue_slug, venue_slug.title())),
        "distance_m": distance_m,
        "off_time": off.group(1) if off else None,
        "runners": runners,
    }


def build_racing_sports(iso_date: str) -> dict:
    blob = json.loads(RS_MAIN.read_text())["result"]["value"]["data"]
    blob["newmarket-rowley"] = json.loads(RS_NEWMARKET.read_text())["result"]["value"]["data"]
    patch_path = DATA / "rs_patch_ayr_r5.json"
    if patch_path.exists():
        patch = json.loads(patch_path.read_text())
        races = blob.get(patch["venue_slug"]) or []
        for i, race in enumerate(races):
            if race.get("race_number") == patch.get("race_number"):
                races[i] = {**race, **{k: patch[k] for k in ("runners", "going", "distance_f") if k in patch}}
        blob[patch["venue_slug"]] = races
    meetings = []
    for slug, races in blob.items():
        if not races:
            continue
        meetings.append({
            "venue": VENUE_TITLES.get(slug, slug.replace("-", " ").title()),
            "venue_slug": slug,
            "date": iso_date,
            "races": [_rs_race(slug, race) for race in races],
        })
    return {"source": "racing_sports", "date": iso_date, "meetings": meetings}


def main() -> int:
    iso = "2026-09-19"
    DATA.mkdir(exist_ok=True)
    punters = build_punters(iso)
    racing = build_racing_sports(iso)
    (DATA / f"punters_{iso}.json").write_text(json.dumps(punters, indent=2))
    (DATA / f"racing_sports_{iso}.json").write_text(json.dumps(racing, indent=2))
    card = merge_and_score(punters, racing)
    out = DATA / f"card_{iso}.json"
    out.write_text(json.dumps(card, indent=2))
    plays = card.get("plays") or []
    print(
        f"Saved {out} — {len(card.get('meetings') or [])} meetings, "
        f"{sum(len(m.get('races') or []) for m in card['meetings'])} races, "
        f"{len(plays)} WIN plays"
    )
    for play in plays:
        print(
            f"  PLAY {play.get('venue')} R{play.get('race_number')} "
            f"{play.get('name')} @{play.get('odds')} edge={play.get('edge')} "
            f"stake={play.get('stake_pct')}% fig={play.get('figure')} wt={play.get('weight_swing')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
