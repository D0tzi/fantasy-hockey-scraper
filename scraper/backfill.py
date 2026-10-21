"""
One-time (or occasional) LOCAL backfill: walks backward from yesterday to
YAHOO_SEASON_START, scraping each day's lineup into docs/history.json, so
season totals aren't limited to only the days since the hourly Action
started running.

Meant to run on your own machine (reuses storage_state.json), NOT in the
GitHub Action - a full-season backfill is too slow/heavy for a schedule.
Run it once, review docs/history.json, then commit + push it yourself.

    python backfill.py
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from config import SEASON_START, YAHOO_TIMEZONE
from scrape import load_history, save_history, scrape_day


def main() -> None:
    if not SEASON_START:
        print("Set YAHOO_SEASON_START (YYYY-MM-DD) before running a backfill.")
        return

    start = date.fromisoformat(SEASON_START)
    today = datetime.now(YAHOO_TIMEZONE).date()
    history = load_history()

    day = start
    while day < today:
        key = day.isoformat()
        if key not in history:
            print(f"Scraping {key}...")
            history[key] = scrape_day(day)
            save_history(history)  # save incrementally in case of interruption
        day += timedelta(days=1)

    print("Backfill complete. Review docs/history.json, then commit + push it.")


if __name__ == "__main__":
    main()
