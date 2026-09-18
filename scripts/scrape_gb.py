#!/usr/bin/env python3
"""Scrape Punters + Racing & Sports GB cards and write a scored overlay."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scrapers.browser import close_browser, launch_browser, load_secrets
from src.scrapers.merge import merge_and_score
from src.scrapers.punters import scrape_punters_gb
from src.scrapers.racing_sports import scrape_racing_sports_gb

DATA = ROOT / "data"


def default_card_date() -> str:
    today = date.today()
    if today.weekday() == 4:  # Friday evening → Saturday GB cards
        return (today + timedelta(days=1)).isoformat()
    return today.isoformat()



def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=default_card_date())
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    iso = args.date
    datetime.strptime(iso, "%Y-%m-%d")
    load_secrets()
    DATA.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    sectional_store: dict = {}
    with sync_playwright() as p:
        browser, ctx = launch_browser(p, headless=args.headless)
        page = ctx.new_page()
        try:
            punters = scrape_punters_gb(page, ctx, iso, log, sectional_store)
            (DATA / f"punters_{iso}.json").write_text(json.dumps(punters, indent=2))
            racing = scrape_racing_sports_gb(page, iso, log)
            (DATA / f"racing_sports_{iso}.json").write_text(json.dumps(racing, indent=2))
        finally:
            close_browser(browser, page)

    card = merge_and_score(punters, racing)
    out = DATA / f"card_{iso}.json"
    out.write_text(json.dumps(card, indent=2))
    plays = card.get("plays") or []
    log(f"Saved {out} — {len(card.get('meetings') or [])} meetings, {len(plays)} WIN plays")
    for play in plays:
        log(
            f"  PLAY {play.get('venue')} R{play.get('race_number')} "
            f"{play.get('name')} @{play.get('odds')} edge={play.get('edge')} "
            f"stake={play.get('stake_pct')}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
