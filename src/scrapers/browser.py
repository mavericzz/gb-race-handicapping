"""Shared Playwright browser for Punters and Racing & Sports."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
_SIBLING_ENV = Path("/Users/toshasharma/Downloads/Github/sectionalscarper/.env")


def load_secrets() -> None:
    load_dotenv(ROOT / ".env")
    if _SIBLING_ENV.exists():
        load_dotenv(_SIBLING_ENV, override=False)


def launch_browser(playwright, *, headless: bool = False):
    cdp_url = os.environ.get("PUNTERS_CDP_URL")
    use_cdp = os.environ.get("PUNTERS_USE_CDP", "").lower() in {"1", "true", "yes"}
    if use_cdp and cdp_url:
        try:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-GB",
                timezone_id="Europe/London",
            )
            browser._is_cdp = True  # type: ignore[attr-defined]
            return browser, ctx
        except Exception:
            pass
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="en-GB",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        timezone_id="Europe/London",
    )
    try:
        from playwright_stealth import Stealth

        Stealth().apply_stealth_sync(ctx)
    except Exception:
        pass
    browser._is_cdp = False  # type: ignore[attr-defined]
    return browser, ctx


def close_browser(browser, page=None) -> None:
    if page is not None:
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass
    if not getattr(browser, "_is_cdp", False):
        try:
            browser.close()
        except Exception:
            pass
