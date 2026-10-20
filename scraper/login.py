"""
One-time local setup: open a real browser, log into Yahoo Fantasy Hockey by
hand (including any 2FA), then save the authenticated session (cookies +
storage) to storage_state.json.

Run this once locally:
    python login.py

Afterwards, copy the *contents* of storage_state.json into a GitHub Actions
secret named YAHOO_STORAGE_STATE (see ../README.md) - never commit this
file, and never share it; it grants full access to your Yahoo account.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright

STORAGE_STATE_PATH = "storage_state.json"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://hockey.fantasysports.yahoo.com/")

        print("A browser window has opened.")
        print("Log in to your Yahoo account (complete 2FA if asked), then")
        print("navigate to your fantasy hockey team's roster page so the")
        print("session is fully established.")
        input("Once you can see your team roster, press Enter here to save the session... ")

        context.storage_state(path=STORAGE_STATE_PATH)
        print(f"Saved session to {STORAGE_STATE_PATH}")
        print("Copy its *contents* into a GitHub secret named YAHOO_STORAGE_STATE.")

        browser.close()


if __name__ == "__main__":
    main()
