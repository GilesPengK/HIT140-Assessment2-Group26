"""Step 2 — scrape per-match team statistics from the FIFA match pages.

Why a browser is needed: possession, fouls, passes and the rest are rendered
client-side. They are not in the page source and there is no public JSON
endpoint for them (checked: /api/v3/live/... returns BallPossession = null,
/api/v3/statistics/... is a 404). So we drive a real browser and read the DOM
after it has rendered.

The page lazy-loads on scroll, so we scroll to the bottom before reading.

This script only downloads and stores the rendered text, one file per match.
Parsing happens in build_dataset.py, so a parser change never means
re-scraping the site.

Setup (once):
    /opt/anaconda3/envs/test06/bin/pip install playwright
    /opt/anaconda3/envs/test06/bin/playwright install chromium

Run:  python src/scrape_match_stats.py
Out:  data/raw/pages/<match_id>.txt   (104 files)
"""

import sys
import time

from playwright.sync_api import sync_playwright

from config import MATCH_INDEX, RAW, PAGE_DELAY, USER_AGENT, page_url

PAGES = RAW / "pages"
PAGES.mkdir(parents=True, exist_ok=True)

MARKER = "FIFA Official Stats"


def scroll_to_bottom(page, steps=14, pause=350):
    """The stats blocks mount as they enter the viewport."""
    for _ in range(steps):
        page.mouse.wheel(0, 2200)
        page.wait_for_timeout(pause)


def scrape_one(page, stage_id, match_id):
    page.goto(page_url(stage_id, match_id), timeout=60_000)
    page.wait_for_timeout(2500)
    scroll_to_bottom(page)

    text = page.inner_text("body")

    # One retry: slow networks sometimes leave the stats block unmounted.
    if MARKER not in text:
        page.wait_for_timeout(2500)
        scroll_to_bottom(page, steps=8)
        text = page.inner_text("body")

    return text


def main():
    todo = [
        (stage_id, match_id)
        for stage_id, _name, _grp, match_id in MATCH_INDEX
        if not (PAGES / f"{match_id}.txt").exists()
    ]

    if not todo:
        print(f"All 104 pages already downloaded in {PAGES}. Nothing to do.")
        return

    print(f"{len(todo)} matches to fetch (already have {104 - len(todo)}).")

    ok, missing_stats, failed = 0, [], []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            user_agent=USER_AGENT, viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()

        for i, (stage_id, match_id) in enumerate(todo, 1):
            try:
                text = scrape_one(page, stage_id, match_id)
            except Exception as exc:
                failed.append((match_id, repr(exc)))
                print(f"[{i:3d}/{len(todo)}] {match_id}  FAILED  {exc}")
                continue

            (PAGES / f"{match_id}.txt").write_text(text, encoding="utf-8")

            if MARKER in text:
                ok += 1
                print(f"[{i:3d}/{len(todo)}] {match_id}  ok  ({len(text)} chars)")
            else:
                missing_stats.append(match_id)
                print(f"[{i:3d}/{len(todo)}] {match_id}  saved but NO STATS BLOCK")

            time.sleep(PAGE_DELAY)

        browser.close()

    print(f"\n{ok} pages with a stats block, {len(missing_stats)} without, {len(failed)} failed.")
    if missing_stats:
        print("No stats block (delete these .txt files and rerun):")
        print("  ", missing_stats)
    if failed:
        print("Errors:")
        for mid, err in failed:
            print("  ", mid, err)
        sys.exit(1)


if __name__ == "__main__":
    main()
