"""Shared configuration, read from environment variables (GitHub Actions
secrets/variables in CI, or exported locally for testing)."""

from __future__ import annotations

import os

LEAGUE_ID = os.environ["YAHOO_LEAGUE_ID"]
TEAM_ID = os.environ["YAHOO_TEAM_ID"]
STORAGE_STATE_PATH = os.environ.get("STORAGE_STATE_PATH", "storage_state.json")

# First day of your league's season (YYYY-MM-DD). Used by backfill.py, and
# to know how far back season totals should start. Leave blank to only
# accumulate from whenever the hourly Action first ran.
SEASON_START = os.environ.get("YAHOO_SEASON_START", "")

TEAM_URL = f"https://hockey.fantasysports.yahoo.com/hockey/{LEAGUE_ID}/{TEAM_ID}"

# Roster slots that do NOT count as "started" for a given day.
BENCH_SLOTS = {"BN", "IR", "IR+", "IR-LT", "NA"}

# All slot/position abbreviations Yahoo uses for NHL rosters (used to find
# the slot token in a scraped roster row).
KNOWN_SLOTS = {"C", "LW", "RW", "D", "G", "F", "UTIL", "BN", "IR", "IR+", "IR-LT", "NA"}
