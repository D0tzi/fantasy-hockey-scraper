"""
Scrapes today's Yahoo Fantasy Hockey roster/lineup, appends it to
docs/history.json, and regenerates docs/payload.json with day/week/season
point totals - counting only points scored while a player was in the
active (started) lineup slot, never while benched/IR.

Used both by the GitHub Action (scheduled hourly) and locally for testing:
    python scrape.py

NOTE ON SELECTORS: Yahoo's fantasy pages are not publicly inspectable
without a logged-in session, so the parsing below is a best-effort based on
the well-established Yahoo Fantasy Sports page conventions (a roster table
with one row per player, a player link to /hockey/players/<id>, a slot
abbreviation like C/LW/RW/D/G/BN/IR, and a trailing numeric points column).
If scrape_day() isn't finding your players, run debug_dump.py to inspect
the real page and adjust parse_roster_rows() accordingly.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from playwright.sync_api import Locator, sync_playwright

from config import BENCH_SLOTS, KNOWN_SLOTS, SEASON_START, STORAGE_STATE_PATH, TEAM_URL

DOCS_DIR = Path(__file__).parent.parent / "docs"
HISTORY_PATH = DOCS_DIR / "history.json"
PAYLOAD_PATH = DOCS_DIR / "payload.json"


def scrape_day(day: date) -> dict:
    """Scrape the roster/lineup for a single date and return {player_name: {...}}."""
    url = f"{TEAM_URL}?date={day.isoformat()}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=STORAGE_STATE_PATH)
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)  # let late client-side rendering settle

        result = parse_roster_rows(page.locator("table tbody tr").all())
        browser.close()
        return result


def parse_roster_rows(rows: list[Locator]) -> dict:
    result = {}
    for row in rows:
        row_text = row.inner_text().strip()
        if not row_text:
            continue

        name_link = row.locator('a[href*="/hockey/players/"]').first
        if name_link.count() == 0:
            continue
        name = name_link.inner_text().strip()
        if not name:
            continue

        tokens = [t.strip() for t in row_text.split("\n") if t.strip()]
        slot = next((t for t in tokens if t.upper() in KNOWN_SLOTS), None)

        result[name] = {
            "slot": slot,
            "started": slot is not None and slot.upper() not in BENCH_SLOTS,
            "points": _extract_points(tokens),
            "game_info": _extract_game_info(row_text),
        }
    return result


def _extract_points(tokens: list[str]) -> Optional[float]:
    """Heuristic: the last purely-numeric (possibly decimal) token is the day's points."""
    for token in reversed(tokens):
        if re.fullmatch(r"-?\d+(\.\d+)?", token):
            return float(token)
    return None


def _extract_game_info(row_text: str) -> Optional[str]:
    """Heuristic: look for 'vs XXX' / '@ XXX' opponent patterns or a game time."""
    match = re.search(r"(vs|@)\s*[A-Z]{2,3}", row_text)
    if match:
        return match.group(0)
    match = re.search(r"\d{1,2}:\d{2}\s*(AM|PM|am|pm)", row_text)
    if match:
        return match.group(0)
    return None


def load_history() -> dict:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return {}


def save_history(history: dict) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, sort_keys=True))


def week_start(day: date) -> date:
    """Yahoo's default NHL fantasy week is Monday-Sunday; adjust here if yours differs."""
    return day - timedelta(days=day.weekday())


def build_payload(history: dict, today: date) -> dict:
    week_begin = week_start(today)
    season_begin = date.fromisoformat(SEASON_START) if SEASON_START else None
    players: dict = {}

    for day_str, day_data in history.items():
        day = date.fromisoformat(day_str)
        if season_begin is not None and day < season_begin:
            continue

        for name, info in day_data.items():
            entry = players.setdefault(name, {
                "name": name,
                "position": None,
                "week_points": 0.0,
                "season_points": 0.0,
                "today": None,
            })

            if info.get("started") and info.get("slot"):
                entry["position"] = info["slot"]

            points = info.get("points") or 0.0
            if info.get("started"):
                if week_begin <= day <= today:
                    entry["week_points"] += points
                entry["season_points"] += points

            if day == today:
                entry["today"] = {
                    "started": info.get("started"),
                    "points": info.get("points"),
                    "slot": info.get("slot"),
                    "game_info": info.get("game_info"),
                }

    return {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "week_start": week_begin.isoformat(),
        "players": list(players.values()),
    }


def main() -> None:
    today = date.today()
    history = load_history()
    history[today.isoformat()] = scrape_day(today)
    save_history(history)

    payload = build_payload(history, today)
    PAYLOAD_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {PAYLOAD_PATH} with {len(payload['players'])} players")


if __name__ == "__main__":
    main()
