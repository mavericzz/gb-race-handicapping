"""Parse Punters runner blocks and Racing & Sports form rows."""

from __future__ import annotations

import re
from datetime import datetime


KG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.I)
ST_LB_RE = re.compile(r"(\d+)\s*st(?:\s*(\d+)\s*l?bs?)?", re.I)
VENUE_ALIASES = {
    "newmarketrowley": "newmarket",
    "newmarketjuly": "newmarket",
    "wolverhamptonaw": "wolverhampton",
}
PLACE_RE = re.compile(
    r"Place\s+(\d+)(?:st|nd|rd|th)?\s+of\s+(\d+)(?:\s*\(([\d.]+)L\))?",
    re.I,
)
DATE_RE = re.compile(r"Date\s+(\d{1,2}/\d{1,2}/\d{2,4})", re.I)
DIST_RE = re.compile(r"Distance\s+(\d+)\s*m", re.I)
TRACK_RE = re.compile(r"Track\s+([A-Za-z][A-Za-z \-']+?)(?:\s+Distance|\s+Class|\s+Track/Con)", re.I)
GOING_RE = re.compile(r"Track/Con\s+([A-Za-z0-9 /]+?)(?:\s+Weight|\s+Runner|$)", re.I)
WEIGHT_RE = re.compile(r"Weight\s+(\d+(?:\.\d+)?)\s*kg", re.I)
TIME_RE = re.compile(r"Runner Time\s+(\d{1,2}):(\d{2}(?:\.\d+)?)", re.I)
CLASS_RE = re.compile(r"Class\s+([A-Z0-9]+)", re.I)
ODDS_RE = re.compile(r"\$?\s*(\d+(?:\.\d+)?)")


def parse_decimal_odds(text: str | None) -> float | None:
    if not text:
        return None
    raw = str(text).strip().replace("$", "").replace(",", "")
    if raw in {"SP", "SCR", "-", ""}:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    return val if val > 1.0 else None


def parse_time_to_seconds(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d{1,2}):(\d{2}(?:\.\d+)?)", text)
    if not m:
        try:
            return float(text)
        except ValueError:
            return None
    return int(m.group(1)) * 60 + float(m.group(2))


def parse_last_start_block(text: str) -> dict:
    """Parse Punters 'Last Start Statistics' blob."""
    out: dict = {}
    place = PLACE_RE.search(text or "")
    if place:
        out["finish"] = int(place.group(1))
        out["field_size"] = int(place.group(2))
        out["beaten_lengths"] = float(place.group(3)) if place.group(3) else (
            0.0 if out["finish"] == 1 else None
        )
    date_m = DATE_RE.search(text or "")
    if date_m:
        raw = date_m.group(1)
        for fmt in ("%d/%m/%y", "%d/%m/%Y"):
            try:
                out["date"] = datetime.strptime(raw, fmt).date().isoformat()
                break
            except ValueError:
                continue
    dist = DIST_RE.search(text or "")
    if dist:
        out["distance_m"] = int(dist.group(1))
    track = TRACK_RE.search(text or "")
    if track:
        out["track"] = track.group(1).strip()
    going = GOING_RE.search(text or "")
    if going:
        out["going"] = going.group(1).strip()
    weight = WEIGHT_RE.search(text or "")
    if weight:
        out["weight_kg"] = float(weight.group(1))
    t = TIME_RE.search(text or "")
    if t:
        out["time_s"] = int(t.group(1)) * 60 + float(t.group(2))
    klass = CLASS_RE.search(text or "")
    if klass:
        out["class_code"] = klass.group(1)
    return out


def parse_kg(text: str | None) -> float | None:
    if text is None:
        return None
    m = KG_RE.search(str(text))
    if m:
        return float(m.group(1))
    try:
        val = float(str(text).strip())
        return val if val > 20 else val  # already kg-ish
    except ValueError:
        return None


def horse_key(name: str) -> str:
    stripped = re.sub(r"\([^)]*\)", "", name or "")
    return re.sub(r"[^a-z0-9]+", "", stripped.lower())


def venue_key(name: str) -> str:
    key = horse_key(name or "")
    return VENUE_ALIASES.get(key, key)


def race_number_from_url(url: str) -> int | None:
    m = re.search(r"race-(\d+)", url, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"/R(\d+)\b", url, re.I)
    if m:
        return int(m.group(1))
    return None


def compact_date(iso_date: str) -> str:
    return iso_date.replace("-", "")


def parse_st_lb(text: str | None) -> int | None:
    if not text:
        return None
    m = ST_LB_RE.search(str(text))
    if not m:
        return None
    return int(m.group(1)) * 14 + int(m.group(2) or 0)


def lbs_to_kg(lbs: float) -> float:
    return round(float(lbs) / 2.20462, 2)


def parse_distance_m(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(text))
    if not m:
        return None
    val = float(m.group(1))
    if val > 200:
        return val
    return round(val * 201.168, 1)
