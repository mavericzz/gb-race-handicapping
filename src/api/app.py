"""Local GB handicapper desk."""

from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
FRONTEND = ROOT / "frontend"

app = FastAPI(title="GB Race Handicapper")
_scrape_lock = threading.Lock()
_scrape_status = {"running": False, "log": []}


def default_card_date() -> str:
    today = date.today()
    if today.weekday() == 4:
        return (today + timedelta(days=1)).isoformat()
    return today.isoformat()


if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


@app.get("/styles.css")
def styles():
    return FileResponse(FRONTEND / "styles.css", media_type="text/css")


@app.get("/app.js")
def app_js():
    return FileResponse(FRONTEND / "app.js", media_type="text/javascript")


@app.get("/card.json")
def card_json():
    path = FRONTEND / "card.json"
    if not path.exists():
        raise HTTPException(404, "card snapshot missing")
    return FileResponse(path, media_type="application/json")


def _latest_card() -> Path | None:
    cards = sorted(DATA.glob("card_*.json"))
    return cards[-1] if cards else None


@app.get("/")
def index():
    index_path = FRONTEND / "index.html"
    if not index_path.exists():
        raise HTTPException(404, "frontend missing")
    return FileResponse(index_path)


@app.get("/api/card")
def card(date_str: str | None = None):
    path = DATA / f"card_{date_str}.json" if date_str else _latest_card()
    if path is None or not path.exists():
        return {"date": date_str or date.today().isoformat(), "meetings": [], "plays": [], "empty": True}
    return json.loads(path.read_text())


@app.get("/api/status")
def status():
    return _scrape_status


@app.post("/api/scrape")
def scrape(date_str: str | None = None):
    iso = date_str or default_card_date()
    if not _scrape_lock.acquire(blocking=False):
        return {"ok": False, "error": "scrape already running"}

    def run():
        _scrape_status["running"] = True
        _scrape_status["log"] = [f"Scraping {iso}"]
        try:
            import subprocess
            import sys
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "scrape_gb.py"), "--date", iso],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=3600,
            )
            _scrape_status["log"] = (proc.stdout or proc.stderr or "").splitlines()[-80:]
            _scrape_status["code"] = proc.returncode
        except Exception as exc:
            _scrape_status["log"].append(str(exc))
        finally:
            _scrape_status["running"] = False
            _scrape_lock.release()

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True, "date": iso}
