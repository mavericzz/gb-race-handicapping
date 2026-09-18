"""Scrape GB meetings from punters.com.au: runners, weights, last-run, sectionals."""

from __future__ import annotations

import csv
import io
import os
import random
import re
import time
from urllib.parse import unquote

from src.scrapers.parsers import (
    compact_date,
    horse_key,
    lbs_to_kg,
    parse_decimal_odds,
    parse_distance_m,
    parse_kg,
    parse_last_start_block,
    race_number_from_url,
)

BASE = "https://www.punters.com.au"

EXTRACT_MEETINGS_JS = """
() => {
  const cards = Array.from(document.querySelectorAll('a.event-card[href*="form-guide/horses/"]'));
  const out = [];
  for (const a of cards) {
    const analytics = a.getAttribute('data-analytics') || '';
    if (!/United Kingdom/i.test(analytics)) continue;
    out.push({
      href: a.href,
      analytics,
      time: (a.querySelector('.event-status__time') || {}).textContent || '',
    });
  }
  return out;
}
"""

EXTRACT_RACE_JS = """
() => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const title = norm((document.querySelector('h1, h2') || {}).textContent);
  const body = document.body.innerText || '';
  const goingM = body.match(/\\n(Soft|Good|Heavy|Firm|Standard|Good to Soft|Good to Firm)[^\\n]*/);
  const distM = body.match(/(\\d{3,4})m/);
  const csv = Array.from(document.querySelectorAll('a[href*=".csv"]')).map(a => a.href);
  const rows = [];
  document.querySelectorAll('tr.form-guide-overview-selection').forEach(row => {
    const sel = row.querySelector('.selection-runner');
    if (!sel) return;
    const r = {};
    const flucsGraph = row.querySelector('.flucs-graph');
    r.selection_id = flucsGraph ? flucsGraph.getAttribute('id') : '';
    const competitor = row.querySelector('.selection-runner__competitor');
    if (competitor) {
      const txt = norm(competitor.textContent);
      const numMatch = txt.match(/^(\\d+)\\./);
      r.number = numMatch ? parseInt(numMatch[1], 10) : null;
      const barrMatch = txt.match(/\\((\\d+)\\)\\s*$/);
      r.barrier = barrMatch ? parseInt(barrMatch[1], 10) : null;
      const horseLink = competitor.querySelector('a[href*="/horses/"]');
      if (horseLink) {
        r.name = norm(horseLink.textContent);
        r.horse_url = horseLink.getAttribute('href') || '';
      } else {
        r.name = txt.replace(/^\\d+\\.\\s*/, '').replace(/\\(\\d+\\)\\s*$/, '').trim();
      }
    }
    const jockeyBlock = row.querySelector('[class*="selection-runner__jockey"]');
    if (jockeyBlock) {
      const jockeyLink = jockeyBlock.querySelector('a[href*="/jockeys/"]');
      r.jockey = jockeyLink ? norm(jockeyLink.textContent) : '';
      const jb = norm(jockeyBlock.textContent);
      const wMatch = jb.match(/\\((\\d+(?:\\.\\d+)?)kg\\)/);
      if (wMatch) r.weight_kg = parseFloat(wMatch[1]);
      const claimMatch = jb.match(/\\(a-?(\\d+(?:\\.\\d+)?)\\)/);
      if (claimMatch) r.claim_kg = parseFloat(claimMatch[1]);
    }
    const trainerBlock = row.querySelector('[class*="selection-runner__trainer"]');
    if (trainerBlock) {
      const trainerLink = trainerBlock.querySelector('a[href*="/trainers/"]');
      r.trainer = trainerLink ? norm(trainerLink.textContent) : '';
    }
    const oddsEl = row.querySelector('.form-guide-overview-selection__odds .base-odds span, .form-guide-overview-selection__odds span');
    if (oddsEl) r.odds_text = norm(oddsEl.textContent);
    const ratingEl = row.querySelector('[class*="rating"]');
    r.rating_text = ratingEl ? norm(ratingEl.textContent) : '';
    let detail = row.nextElementSibling;
    let hops = 0;
    while (detail && hops < 3 && !detail.querySelector('.form-guide-overview-selection-details, .form-guide-overview-selection-details__comment-content')) {
      if (detail.querySelector('.selection-runner')) { detail = null; break; }
      detail = detail.nextElementSibling;
      hops++;
    }
    if (detail) {
      r.detail_text = norm(detail.innerText || '');
    }
    if ((row.className || '').includes('scratched')) r.scratched = true;
    rows.push(r);
  });
  return { title, going: goingM ? goingM[1] : '', distance_m: distM ? parseInt(distM[1], 10) : null, csv, runners: rows };
}
"""


def _sleep(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def _goto(page, url: str, log, timeout: int = 90000) -> None:
    last = None
    for attempt in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(2000)
            return
        except Exception as exc:
            last = exc
            log(f"  goto retry {attempt + 1}: {exc}")
            page.wait_for_timeout(1500)
    raise last


def _login(page, log) -> None:
    email = os.environ.get("PUNTER_EMAIL") or os.environ.get("PUNTERS_EMAIL")
    password = os.environ.get("PUNTER_PASSWORD") or os.environ.get("PUNTERS_PASSWORD")
    _goto(page, f"{BASE}/form-guide/", log, timeout=60000)
    page.wait_for_timeout(2500)
    if page.locator('text=Log In').count() == 0:
        log("Punters session already authenticated (or login hidden).")
        return
    if not email or not password:
        log("No Punters credentials — scraping public form only.")
        return
    try:
        page.locator('text=Log In').first.click(timeout=5000)
        page.wait_for_timeout(1500)
        page.fill('input[type="email"], input[name="username"]', email, timeout=8000)
        page.fill('input[type="password"]', password, timeout=8000)
        page.locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")').first.click()
        page.wait_for_timeout(4000)
        log("Punters login submitted.")
    except Exception as exc:
        log(f"Punters login skipped: {exc}")


def _dismiss(page) -> None:
    try:
        page.evaluate(
            """() => {
              document.querySelectorAll('[class*="campaign"], [id*="campaign"]').forEach(el => el.remove());
              document.body.style.overflow = 'auto';
            }"""
        )
        page.keyboard.press("Escape")
    except Exception:
        pass


def collect_gb_race_urls(page, iso_date: str, log) -> list[dict]:
    compact = compact_date(iso_date)
    _goto(page, f"{BASE}/form-guide/?date={iso_date}", log, timeout=90000)
    page.wait_for_timeout(5000)
    _dismiss(page)
    try:
        page.evaluate("""() => {
          const tab = Array.from(document.querySelectorAll('[role=tab]')).find(el => /international/i.test((el.textContent||'').trim()));
          if (tab) tab.click();
        }""")
        page.wait_for_timeout(4000)
    except Exception as exc:
        log(f"  International tab: {exc}")
    _dismiss(page)
    try:
        page.wait_for_selector("a.event-card", timeout=15000)
    except Exception:
        log("  No event-card selector; title=" + (page.title() or ""))
    raw = page.evaluate(EXTRACT_MEETINGS_JS) or []
    log(f"  event cards with UK analytics: {len(raw)} / page cards")
    races = []
    for item in raw:
        href = item.get("href") or ""
        if compact not in href:
            continue
        m = re.search(r"form-guide/horses/([^/]+)/([^/#]+)", href)
        venue_slug = m.group(1) if m else ""
        races.append({
            "url": href.split("#")[0],
            "venue_slug": venue_slug,
            "venue": venue_slug.replace("-uk-" + compact, "").replace("-", " ").title(),
            "race_number": race_number_from_url(href),
            "off_time": item.get("time") or "",
        })
    log(f"Punters: {len(races)} GB races on {iso_date}")
    return races


def _fetch_csv(ctx, url: str, log) -> list[dict]:
    try:
        resp = ctx.request.get(url, timeout=30000)
        if resp.status != 200:
            log(f"  CSV HTTP {resp.status}")
            return []
        reader = csv.DictReader(io.StringIO(resp.text()))
        rows = [dict(r) for r in reader]
        log(f"  Form CSV: {len(rows)} runners")
        return rows
    except Exception as exc:
        log(f"  CSV failed: {exc}")
        return []


def _parse_runner(raw: dict, csv_row: dict | None) -> dict:
    last = parse_last_start_block(raw.get("detail_text") or "")
    rating = None
    if csv_row:
        try:
            rating = float(csv_row.get("Handicap Rating") or "")
        except ValueError:
            rating = None
        if not last.get("finish"):
            try:
                last["finish"] = int(float(csv_row.get("Last Start Finish Position") or 0)) or None
            except ValueError:
                pass
        if last.get("beaten_lengths") is None:
            try:
                last["beaten_lengths"] = float(csv_row.get("Last Start Margin") or "")
            except ValueError:
                pass
        if not last.get("distance_m"):
            last["distance_m"] = parse_distance_m(csv_row.get("Last Start Distance"))
    odds = parse_decimal_odds(raw.get("odds_text") or (csv_row or {}).get("Best Fixed Odds"))
    weight = raw.get("weight_kg") or parse_kg(raw.get("silk") or "")
    if weight is None and csv_row:
        try:
            lbs = float(csv_row.get("Weight Carried") or csv_row.get("Weight") or 0)
            if lbs > 40:
                weight = lbs_to_kg(lbs)
        except ValueError:
            pass
    return {
        "name": raw.get("name") or (csv_row or {}).get("Horse Name"),
        "key": horse_key(raw.get("name") or (csv_row or {}).get("Horse Name") or ""),
        "number": raw.get("number"),
        "barrier": raw.get("barrier") or (int(csv_row["Barrier"]) if csv_row and csv_row.get("Barrier") else None),
        "jockey": raw.get("jockey") or (csv_row or {}).get("Jockey"),
        "trainer": raw.get("trainer") or (csv_row or {}).get("Trainer"),
        "weight_kg": weight,
        "claim_kg": raw.get("claim_kg"),
        "handicap_rating": rating,
        "odds": odds,
        "scratched": bool(raw.get("scratched")),
        "last_run": last,
        "source": "punters",
        "selection_id": raw.get("selection_id"),
        "csv": csv_row or {},
    }


def scrape_punters_gb(page, ctx, iso_date: str, log, sectional_store: dict) -> dict:
    _login(page, log)
    race_urls = collect_gb_race_urls(page, iso_date, log)
    meetings: dict[str, dict] = {}

    def on_response(response):
        if "getSectionalsBySelectionIds" not in response.url:
            return
        try:
            body = response.json()
            competitors = body.get("data", {}).get("competitorForms", [])
            parsed = []
            for comp in competitors:
                sid = comp.get("selectionId", "")
                for form in comp.get("forms", []):
                    entry = {
                        "selection_id": sid,
                        "finish_position": form.get("finishPosition"),
                        "meeting_date": form.get("meetingDate"),
                        "distance": form.get("eventDistance"),
                        "track_condition": form.get("trackCondition"),
                        "finish_time": form.get("finishTime"),
                        "venue": (form.get("venue") or {}).get("name", ""),
                        "event_name": form.get("eventNameForm"),
                    }
                    summary = form.get("sectionalTimeSummary") or {}
                    entry["early_speed"] = summary.get("earlySpeed")
                    entry["late_speed"] = summary.get("lateSpeed")
                    splits = form.get("sectionalTime") or {}
                    for key in ("l800", "l600", "l400", "l200", "finish"):
                        split = splits.get(key) or {}
                        entry[f"{key}_split"] = split.get("split")
                        entry[f"{key}_speed"] = split.get("speed")
                    parsed.append(entry)
            sectional_store.setdefault("latest_sectionals", []).extend(parsed)
            decoded = unquote(response.url)
            for sid in re.findall(r'"(\d{7,})"', decoded):
                sectional_store.setdefault("latest_selection_ids", [])
                if sid not in sectional_store["latest_selection_ids"]:
                    sectional_store["latest_selection_ids"].append(sid)
        except Exception:
            pass

    page.on("response", on_response)

    for i, race in enumerate(race_urls):
        if i:
            _sleep(2.0, 4.5)
        venue = race["venue"]
        log(f"  Punters {venue} R{race['race_number']}")
        sectional_store.clear()
        try:
            _goto(page, race["url"], log, timeout=90000)
            page.wait_for_timeout(3500)
            _dismiss(page)
            try:
                page.locator("button:has-text('Show All Form'), a:has-text('Show All Form')").first.click(timeout=2500)
                page.wait_for_timeout(1500)
            except Exception:
                pass
            try:
                page.evaluate("""() => {
                  document.querySelectorAll('.form-guide-overview-selection__toggle-button').forEach(b => { try { b.click(); } catch(e) {} });
                }""")
                page.wait_for_timeout(1200)
            except Exception:
                pass
            tab = page.locator('.base-tabs__tab:has-text("Sectionals")')
            if tab.count():
                try:
                    tab.first.click(timeout=4000)
                    page.wait_for_timeout(3500)
                    page.locator('.base-tabs__tab:has-text("Form")').first.click(timeout=3000)
                    page.wait_for_timeout(800)
                except Exception:
                    pass
            extracted = page.evaluate(EXTRACT_RACE_JS) or {}
        except Exception as exc:
            log(f"    failed: {exc}")
            extracted = {"runners": []}

        csv_urls = extracted.get("csv") or []
        csv_rows = _fetch_csv(ctx, csv_urls[0], log) if csv_urls else []
        by_name = {horse_key(r.get("Horse Name") or ""): r for r in csv_rows}
        runners = []
        for raw in extracted.get("runners") or []:
            key = horse_key(raw.get("name") or "")
            runners.append(_parse_runner(raw, by_name.get(key)))
            sid = raw.get("selection_id")
            if sid:
                for entry in sectional_store.get("latest_sectionals") or []:
                    if entry.get("selection_id") == sid:
                        runners[-1].setdefault("sectionals", []).append(entry)

        meeting = meetings.setdefault(venue, {
            "venue": venue,
            "venue_slug": race["venue_slug"],
            "date": iso_date,
            "races": [],
        })
        meeting["races"].append({
            "race_number": race["race_number"],
            "name": extracted.get("title") or "",
            "url": race["url"],
            "going": extracted.get("going"),
            "distance_m": extracted.get("distance_m"),
            "off_time": race.get("off_time"),
            "runners": runners,
        })

    return {"source": "punters", "date": iso_date, "meetings": list(meetings.values())}
