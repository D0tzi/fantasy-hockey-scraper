"""
Debugging helper: loads a given date's team roster page and saves the
rendered HTML + a full-page screenshot, so you can inspect Yahoo's actual
markup and fix parse_roster_rows() in scrape.py if it isn't finding your
players correctly.

    python debug_dump.py [YYYY-MM-DD]
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from config import STORAGE_STATE_PATH, TEAM_URL, YAHOO_TIMEZONE


def main() -> None:
    day = (
        date.fromisoformat(sys.argv[1])
        if len(sys.argv) > 1
        else datetime.now(YAHOO_TIMEZONE).date()
    )
    url = f"{TEAM_URL}?date={day.isoformat()}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE_PATH)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2000)

        Path("debug_page.html").write_text(page.content())
        page.screenshot(path="debug_page.png", full_page=True)
        browser.close()

    print("Saved debug_page.html and debug_page.png for:", url)


if __name__ == "__main__":
    main()
