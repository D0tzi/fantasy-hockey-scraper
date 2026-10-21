"""
Scrapes today's Yahoo Fantasy Hockey roster/lineup, appends it to
docs/history.json, and regenerates docs/payload.json with day/week/season
point totals - counting only points scored while a player was in the
active (started) lineup slot, never while benched/IR.

Used both by the GitHub Action (scheduled hourly) and locally for testing:
    python scrape.py

NOTE ON SELECTORS: Yahoo's fantasy pages are not publicly inspectable
without a logged-in session, so the parsing below is a best-effort based on
Yahoo's roster markup: player links use /nhl/players/<id>, assigned slots
are in td.edit, and fantasy points are in td.pts. If scrape_day() isn't
finding your players, run debug_dump.py to inspect the real page and adjust
parse_roster_rows() accordingly.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Locator, TimeoutError as PlaywrightTimeoutError, sync_playwright

from config import BENCH_SLOTS, KNOWN_SLOTS, SEASON_START, STORAGE_STATE_PATH, TEAM_URL, YAHOO_TIMEZONE

DOCS_DIR = Path(__file__).parent.parent / "docs"
HISTORY_PATH = DOCS_DIR / "history.json"
PAYLOAD_PATH = DOCS_DIR / "payload.json"
PLAYER_LINK_SELECTOR = 'a[href*="/nhl/players/"]'


def scrape_day(day: date) -> dict:
    """Scrape the roster/lineup for a single date and return {player_name: {...}}."""
    url = f"{TEAM_URL}?date={day.isoformat()}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=STORAGE_STATE_PATH)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            rows = page.locator("table tbody tr")
            try:
                rows.first.wait_for(state="attached", timeout=30_000)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(
                    "Yahoo's roster table did not load. Check that the saved "
                    "Yahoo session is still valid and the team URL is correct."
                ) from exc

            result = parse_roster_rows(rows.all())
            if not result:
                page_url = urlunsplit((*urlsplit(page.url)[:3], "", ""))
                page_title = page.title()
                player_links = page.locator(PLAYER_LINK_SELECTOR).count()
                print(
                    "Yahoo page diagnostics: "
                    f"url={page_url!r}, title={page_title!r}, "
                    f"roster_rows={rows.count()}, player_links={player_links}"
                )
                raise RuntimeError(
                    "Yahoo's page loaded, but no players were recognized. "
                    "Check the diagnostics above: a sign-in/consent page means "
                    "the saved session was not accepted; otherwise the roster "
                    "markup may have changed. Run debug_dump.py locally to inspect it."
                )
            return result
        finally:
            browser.close()


def parse_roster_rows(rows: list[Locator]) -> dict:
    result = {}
    for row in rows:
        row_text = row.inner_text().strip()
        if not row_text:
            continue

        name_link = row.locator(PLAYER_LINK_SELECTOR).first
        if name_link.count() == 0:
            continue
        name = name_link.inner_text().strip()
        if not name:
            continue

        tokens = [t.strip() for t in row_text.split("\n") if t.strip()]
        slot_cell = row.locator("td.edit").first
        slot = slot_cell.inner_text().strip().upper() if slot_cell.count() else None
        if slot not in KNOWN_SLOTS:
            slot = next((t.upper() for t in tokens if t.upper() in KNOWN_SLOTS), None)

        points_cell = row.locator("td.pts").first
        points = (
            _parse_points(points_cell.inner_text())
            if points_cell.count()
            else _extract_points(tokens)
        )
        stats = _extract_player_stats(row)

        result[name] = {
            "slot": slot,
            "started": slot is not None and slot.upper() not in BENCH_SLOTS,
            "points": points,
            "stats": stats,
            "game_info": _extract_game_info(row_text),
        }
    return result


def _extract_player_stats(row: Locator) -> dict:
    table = row.locator("xpath=ancestor::table[1]")
    header_rows = table.locator("thead tr")
    if header_rows.count() == 0:
        return {}

    headers = [
        header.inner_text().strip().upper()
        for header in header_rows.last.locator("th, td").all()
    ]
    cells = row.locator("td").all()
    values_by_header = {
        header: _parse_points(cells[index].inner_text())
        for index, header in enumerate(headers)
        if index < len(cells)
    }

    if "SV" in values_by_header and "GA" in values_by_header:
        return {
            "saves": values_by_header.get("SV"),
            "goals_against": values_by_header.get("GA"),
        }

    return {
        "goals": values_by_header.get("G"),
        "assists": values_by_header.get("A"),
        "ppp": values_by_header.get("PPP"),
        "shots": values_by_header.get("SOG"),
        "hits": values_by_header.get("HIT"),
        "blocks": values_by_header.get("BLK"),
    }


def _parse_points(value: str) -> Optional[float]:
    value = value.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", value):
        return float(value)
    return None


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
                    "stats": info.get("stats"),
                    "slot": info.get("slot"),
                    "game_info": info.get("game_info"),
                }

    return {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "updated_at_local": datetime.now(YAHOO_TIMEZONE).isoformat(timespec="minutes"),
        "week_start": week_begin.isoformat(),
        "players": list(players.values()),
    }


def main() -> None:
    today = datetime.now(YAHOO_TIMEZONE).date()
    history = load_history()
    history[today.isoformat()] = scrape_day(today)
    save_history(history)

    payload = build_payload(history, today)
    PAYLOAD_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {PAYLOAD_PATH} with {len(payload['players'])} players")


if __name__ == "__main__":
    main()
