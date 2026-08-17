"""Step 2 — scrape per-match team statistics from the FIFA match pages.

Why a browser is needed: possession, fouls, passes and the rest are rendered
client-side. They are not in the page source and there is no public JSON
endpoint for them (checked: /api/v3/live/... returns BallPossession = null,
/api/v3/statistics/... is a 404, and the CloudFront path only serves
status.json). So we drive a real browser and read the DOM after it renders.

Two things this script has to work around, both found the hard way:

1. **The bot-detection script crashes headless Chromium.** fifa.com serves an
   Akamai sensor script from an obfuscated same-origin path with no file
   extension. With a CDP client attached it kills the browser process with
   SIGTRAP before the page finishes loading. Aborting that one request fixes
   it, and the statistics still render because they come from elsewhere.

2. **The stats mount lazily on scroll**, so the page has to be scrolled to the
   bottom before the text is read.

Images, media and fonts are blocked too — nothing here needs them, and on a
machine with modest RAM it makes 104 page loads noticeably lighter.

Setup (once):
    /opt/anaconda3/envs/test06/bin/pip install --only-binary :all: playwright
    /opt/anaconda3/envs/test06/bin/playwright install chromium

Run:  python src/scrape_match_stats.py
Out:  data/raw/pages/<match_id>.txt   (104 files)
"""

import re
import sys
import time

from playwright.sync_api import sync_playwright

from config import MATCH_INDEX, RAW, PAGE_DELAY, USER_AGENT, page_url

PAGES = RAW / "pages"
PAGES.mkdir(parents=True, exist_ok=True)

MARKER = "FIFA Official Stats"

# Same-origin paths that are neither the app, its assets, nor the manifest.
# In practice this matches only the Akamai sensor script — see note 1 above.
SENSOR = re.compile(
    r"^https://www\.fifa\.com/(?!en/|static/|manifest)[A-Za-z0-9_\-]+/[A-Za-z0-9_\-/]+$"
)
SKIP_TYPES = {"image", "media", "font"}


def _route(route):
    request = route.request
    if SENSOR.match(request.url) or request.resource_type in SKIP_TYPES:
        return route.abort()
    route.continue_()


def scrape_one(page, stage_id, match_id, rounds=6):
    """Load a match page and return its rendered text once the stats appear."""
    page.goto(page_url(stage_id, match_id), timeout=60_000, wait_until="domcontentloaded")

    text = ""
    for _ in range(rounds):
        page.wait_for_timeout(2500)
        for _ in range(6):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(250)
        text = page.inner_text("body")
        if MARKER in text:
            break

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
    started = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}
        )
        context.route("**/*", _route)
        page = context.new_page()

        for i, (stage_id, match_id) in enumerate(todo, 1):
            try:
                text = scrape_one(page, stage_id, match_id)
            except Exception as exc:
                failed.append((match_id, repr(exc)))
                print(f"[{i:3d}/{len(todo)}] {match_id}  FAILED  {type(exc).__name__}")
                continue

            (PAGES / f"{match_id}.txt").write_text(text, encoding="utf-8")

            if MARKER in text:
                ok += 1
                mins = (time.time() - started) / 60
                print(f"[{i:3d}/{len(todo)}] {match_id}  ok  {len(text):5d} chars  ({mins:.1f} min)")
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
        for match_id, err in failed:
            print("  ", match_id, err)
        sys.exit(1)


if __name__ == "__main__":
    main()
