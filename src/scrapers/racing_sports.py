"""Scrape Racing and Sports GB form: weights, past runs, ratings."""

from __future__ import annotations

import re

from src.scrapers.parsers import horse_key, lbs_to_kg, parse_st_lb

BASE = "https://www.racingandsports.co.uk"
GB_VENUES = ["ayr", "chester", "newbury", "newmarket-rowley", "newcastle", "wolverhampton"]
VENUE_TITLES = {
    "newmarket-rowley": "Newmarket",
    "newmarket-july": "Newmarket",
    "wolverhampton-aw": "Wolverhampton",
}

EXTRACT_JS = r"""
() => {
  const parseCard = (el) => {
    const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    const head = t.match(/(\d+)\.\s+(.+?)\s+Wgt:\s+(\d+st(?:\s+\d+l?bs)?)/i);
    if (!head) return null;
    const j = t.match(/J:\s+([A-Z .'-]+)\s+BP:\s+(\d+)/);
    const tr = t.match(/T:\s+([A-Z0-9 .'-]+?)\s+Form/);
    const past = [];
    const re = /(\d{2}-[A-Za-z]{3}-\d{4})\s+([A-Z][A-Z \-']+?)\s+Distance\s+(\d+(?:\.\d+)?f)\s*Runners\s*(\d+)\s*Finished\s*(\d+)[\s\S]*?Weight\s+([\d.-]+)\s*\|\s*([\d.]+)\s*Margin\s*([\d.]+L|SHD|NK|HD|NOSE|NSE)/gi;
    let m;
    while ((m = re.exec(t)) && past.length < 4) {
      past.push({
        date: m[1],
        track: m[2].trim(),
        distance: m[3],
        finish: parseInt(m[5], 10),
        kg: parseFloat(m[7]),
        margin: m[8],
      });
    }
    return {
      number: parseInt(head[1], 10),
      name: head[2].trim(),
      wgt: head[3],
      jockey: j ? j[1].trim() : '',
      barrier: j ? parseInt(j[2], 10) : null,
      trainer: tr ? tr[1].trim() : '',
      past,
    };
  };
  const title = ((document.querySelector('h1, h2') || {}).textContent || '').replace(/\s+/g, ' ').trim();
  const text = document.body.innerText || '';
  const goingM = text.match(/Going:\s*([A-Za-z /]+)/i);
  const distM = title.match(/(\d+(?:\.\d+)?)f/) || text.match(/(\d+(?:\.\d+)?)f/);
  const runners = Array.from(document.querySelectorAll('.mobile-runner')).map(parseCard).filter(Boolean);
  return {
    title,
    going: goingM ? goingM[1].trim() : '',
    distance_f: distM ? distM[1] : '',
    ok: runners.length > 0,
    runners,
    past: {},
  };
}
"""


def furlongs_to_m(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(text))
    if not m:
        return None
    return round(float(m.group(1)) * 201.168, 1)


MARGIN_MAP = {"SHD": 0.1, "HD": 0.2, "NK": 0.25, "NSE": 0.05, "NOSE": 0.05}


def _margin_lengths(text: str | None) -> float | None:
    if not text:
        return None
    raw = str(text).strip().upper()
    if raw in MARGIN_MAP:
        return MARGIN_MAP[raw]
    m = re.search(r"([\d.]+)", raw)
    return float(m.group(1)) if m else None


def _parse_past(races: list[dict]) -> list[dict]:
    out = []
    for race in races or []:
        wgt = parse_st_lb(race.get("jockey_wgt") or race.get("wgt") or "")
        kg = race.get("kg") or race.get("weight_kg")
        if kg is None and wgt:
            kg = lbs_to_kg(wgt)
        out.append({
            "date": race.get("date"),
            "track": race.get("track"),
            "distance_m": furlongs_to_m(race.get("distance")),
            "finish": race.get("finish"),
            "weight_kg": float(kg) if kg not in (None, "") else None,
            "beaten_lengths": _margin_lengths(race.get("margin")),
        })
    return out


def scrape_racing_sports_gb(page, iso_date: str, log, venues: list[str] | None = None) -> dict:
    meetings = []
    for venue in venues or GB_VENUES:
        races = []
        consecutive_misses = 0
        for n in range(1, 11):
            url = f"{BASE}/form-guide/thoroughbred/united-kingdom/{venue}/{iso_date}/R{n}"
            log(f"  R&S {venue} R{n}")
            try:
                resp = None
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception as exc:
                    log(f"    goto retry: {exc}")
                    try:
                        resp = page.goto(url, wait_until="load", timeout=60000)
                    except Exception as exc2:
                        log(f"    failed: {exc2}")
                        consecutive_misses += 1
                        if consecutive_misses >= 2:
                            break
                        continue
                page.wait_for_timeout(2200)
                status = resp.status if resp else 0
                if status >= 400:
                    consecutive_misses += 1
                    if consecutive_misses >= 2:
                        break
                    continue
                data = page.evaluate(EXTRACT_JS) or {}
            except Exception as exc:
                log(f"    failed: {exc}")
                consecutive_misses += 1
                if consecutive_misses >= 2:
                    break
                continue
            if not data.get("ok"):
                consecutive_misses += 1
                if consecutive_misses >= 2:
                    break
                continue
            consecutive_misses = 0
            runners = []
            past_map = data.get("past") or {}
            for raw in data.get("runners") or []:
                lbs = parse_st_lb(raw.get("wgt"))
                name = re.sub(r"\s+", " ", raw.get("name") or "").strip()
                past = raw.get("past") or past_map.get(name) or past_map.get(name.upper()) or []
                runners.append({
                    "name": name.title() if name.isupper() else name,
                    "key": horse_key(name),
                    "number": raw.get("number"),
                    "barrier": raw.get("barrier"),
                    "jockey": (raw.get("jockey") or "").title(),
                    "trainer": (raw.get("trainer") or "").title(),
                    "weight_kg": lbs_to_kg(lbs) if lbs else None,
                    "weight_stlb": raw.get("wgt"),
                    "past_runs": _parse_past(past),
                    "source": "racing_sports",
                })
            races.append({
                "race_number": n,
                "name": data.get("title") or f"{venue} R{n}",
                "url": url,
                "going": data.get("going"),
                "distance_m": furlongs_to_m(data.get("distance_f")),
                "runners": runners,
            })
        if races:
            meetings.append({
                "venue": VENUE_TITLES.get(venue, venue.replace("-", " ").title()),
                "venue_slug": venue,
                "date": iso_date,
                "races": races,
            })
            log(f"  R&S {venue}: {len(races)} races")
    return {"source": "racing_sports", "date": iso_date, "meetings": meetings}
