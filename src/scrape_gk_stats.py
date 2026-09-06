"""
scrape_gk_stats.py

Automated Playwright scraper for FBref goalkeeper match-log pages
(2026 FIFA World Cup).

============================================================================
STATUS: UNVERIFIED. This script has NOT been run against the live fbref.com
site in the environment that wrote it (no network access to fbref.com from
that sandbox). Do NOT write "automated data collection" in the README,
notebook, or slides on the strength of this file alone -- run it yourself,
confirm real HTML actually lands in data/raw/gk_pages/, and only then
update the documentation. If Cloudflare blocks it, that is a genuine,
reportable technical finding (consistent with the "FBref -- not used,
Cloudflare bot protection" note already in the README for team_match.csv),
not a bug to quietly work around by falling back to manual collection
without saying so.
============================================================================

What this does, if it works:
  1. Loads the season goalkeeping stats page and extracts every
     goalkeeper's name, team, and FBref player id.
  2. Visits each goalkeeper's individual match-log page and saves the
     rendered HTML to disk.
  3. Writes a manifest (scrape_manifest.json) recording which goalkeepers
     succeeded, which were blocked, and which errored -- so a partial run
     is still useful and the failure pattern is visible, not hidden.

Run with:
    pip install playwright
    playwright install chromium
    python src/scrape_gk_stats.py

Then run src/build_gk_dataset.py to parse the saved HTML into
data/gk_match.csv (requires pandas.read_html's HTML parser backend --
`pip install lxml html5lib` if it's not already covered by requirements.txt).
"""

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

RAW_DIR = Path("data/raw/gk_pages")
RAW_DIR.mkdir(parents=True, exist_ok=True)

SEASON_STATS_URL = "https://fbref.com/en/comps/1/2026/keepers/2026-World-Cup-Stats"

# Same spirit as src/config.py's REQUEST_DELAY / PAGE_DELAY for the FIFA
# scraper: keep this in place. Do not lower it to "speed things up" --
# hammering a site that already blocks bots is how you get an IP-level ban
# on top of the existing bot-detection, and helps nobody.
REQUEST_DELAY_SECONDS = 5

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

CLOUDFLARE_MARKERS = (
    "Just a moment",
    "cf-browser-verification",
    "Attention Required",
    "Checking your browser",
)


async def new_context(browser):
    """A real desktop browser context -- explicit UA, viewport, and locale,
    since headless defaults with no configuration are themselves an easy
    bot-detection signal."""
    return await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 900},
        locale="en-US",
    )


async def fetch_rendered_html(page, url: str) -> str:
    await page.goto(url, wait_until="networkidle", timeout=30000)
    # FBref's tables can take a moment to finish mounting even after
    # "networkidle" fires -- give it a short settle window.
    await page.wait_for_timeout(1500)
    return await page.content()


def looks_blocked(html: str) -> bool:
    return any(marker in html for marker in CLOUDFLARE_MARKERS)


async def get_goalkeeper_list(page) -> list[dict]:
    """Scrape the season goalkeeping stats page for each goalkeeper's name
    and FBref player id (the id is embedded in their 'Matches' link href,
    e.g. /en/players/5d11fc17/matchlogs/...)."""
    html = await fetch_rendered_html(page, SEASON_STATS_URL)
    (RAW_DIR / "season_stats.html").write_text(html, encoding="utf-8")

    if looks_blocked(html):
        print("BLOCKED fetching the season stats page itself -- stopping early.")
        return []

    # Player id + display name both live inside the same anchor tag pattern
    # on the "Player" column of the goalkeeping table.
    rows = re.findall(
        r'/en/players/([0-9a-f]{8})/[^"]*"[^>]*>([^<]+)</a>', html
    )
    goalkeepers = []
    seen = set()
    for player_id, name in rows:
        if player_id in seen:
            continue
        seen.add(player_id)
        goalkeepers.append({"player_id": player_id, "name": name.strip()})
    return goalkeepers


def slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-")


async def scrape_goalkeeper_matchlog(page, player_id: str, name: str):
    url = (
        f"https://fbref.com/en/players/{player_id}/matchlogs/2026/keeper/"
        f"{slugify(name)}-Match-Logs"
    )
    try:
        html = await fetch_rendered_html(page, url)
    except Exception as e:
        print(f"  ERROR  {name} ({player_id}): {e}")
        return {"status": "error", "detail": str(e), "raw_path": None}

    if looks_blocked(html):
        print(f"  BLOCKED  {name} ({player_id})")
        return {"status": "blocked", "detail": None, "raw_path": None}

    out_path = RAW_DIR / f"{player_id}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  OK       {name} ({player_id}) -> {out_path}")
    return {"status": "ok", "detail": None, "raw_path": str(out_path)}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await new_context(browser)
        page = await context.new_page()

        print("Fetching goalkeeper list from the season stats page...")
        goalkeepers = await get_goalkeeper_list(page)
        print(f"Found {len(goalkeepers)} goalkeepers.\n")

        results = []
        for i, gk in enumerate(goalkeepers, 1):
            print(f"[{i}/{len(goalkeepers)}] {gk['name']}")
            outcome = await scrape_goalkeeper_matchlog(page, gk["player_id"], gk["name"])
            results.append({**gk, **outcome})
            await asyncio.sleep(REQUEST_DELAY_SECONDS)

        await browser.close()

    manifest_path = RAW_DIR / "scrape_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(results, f, indent=2)

    n_ok = sum(r["status"] == "ok" for r in results)
    n_blocked = sum(r["status"] == "blocked" for r in results)
    n_error = sum(r["status"] == "error" for r in results)
    print(f"\nDone. {n_ok}/{len(results)} succeeded, {n_blocked} blocked, {n_error} errored.")
    print(f"Manifest written to {manifest_path}")
    if n_ok < len(results):
        print(
            "\nSome goalkeepers were blocked or failed. This is real data about "
            "whether this approach works, not something to paper over -- report "
            "the actual success rate rather than only the goalkeepers that worked."
        )


if __name__ == "__main__":
    asyncio.run(main())
