"""
build_gk_dataset.py

Parses the HTML pages saved by scrape_gk_stats.py into the shared
data/gk_match.csv format (one row per goalkeeper per World Cup match).

============================================================================
STATUS: UNVERIFIED, same as scrape_gk_stats.py -- this has not been run
against real scraped output in the environment that wrote it. Run
scrape_gk_stats.py first, confirm data/raw/gk_pages/*.html contains real
match-log tables (open one in a browser and check), then run this.
============================================================================

FBref hides several of its tables inside HTML comments to make casual
scraping harder -- this is the same quirk documented for manual copying,
and it applies here too, so comments are unwrapped before parsing.
"""

import json
import re
from io import StringIO
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/gk_pages")
MANIFEST_PATH = RAW_DIR / "scrape_manifest.json"
OUTPUT_PATH = Path("data/gk_match.csv")

# Real, verified advancement status for all 48 teams (cross-checked against
# the official group-stage standings and knockout bracket on Wikipedia).
ADVANCED_TEAMS = {
    "Mexico", "Switzerland", "Brazil", "United States", "Germany", "Netherlands",
    "Belgium", "Spain", "France", "Argentina", "Colombia", "England",
    "South Africa", "Canada", "Morocco", "Australia", "Cote d'Ivoire", "Japan",
    "Egypt", "Cabo Verde", "Norway", "Austria", "Portugal", "Croatia",
    "Bosnia and Herzegovina", "Paraguay", "Ecuador", "Sweden", "Senegal",
    "Algeria", "Congo DR", "Ghana",
}


def get_comment_tables(html: str) -> list[pd.DataFrame]:
    """FBref hides some tables inside <!-- --> comments. Extract and parse
    those in addition to the ones pandas.read_html finds normally."""
    tables = []
    try:
        tables += pd.read_html(StringIO(html))
    except ValueError:
        pass
    for comment in re.findall(r"<!--(.*?)-->", html, re.DOTALL):
        if "<table" in comment:
            try:
                tables += pd.read_html(StringIO(comment))
            except ValueError:
                pass
    return tables


def extract_team_from_squad(squad_value: str) -> str:
    """The 'Squad' column looks like 'jo Jordan' (country-code prefix +
    name) -- strip the prefix."""
    parts = str(squad_value).split(" ", 1)
    return parts[1] if len(parts) == 2 else parts[0]


def parse_goalkeeper_page(html_path: Path, player_name: str) -> pd.DataFrame:
    html = html_path.read_text(encoding="utf-8")
    tables = get_comment_tables(html)

    matchlog = None
    for t in tables:
        cols = [str(c) for c in t.columns]
        if "Comp" in cols and "Round" in cols and "Squad" in cols:
            matchlog = t
            break

    if matchlog is None:
        print(f"  Could not find a match-log table for {player_name} -- skipping.")
        return pd.DataFrame()

    wc = matchlog[matchlog["Comp"] == "World Cup"].copy()
    if wc.empty:
        return pd.DataFrame()

    wc["Player"] = player_name
    wc["Team"] = wc["Squad"].apply(extract_team_from_squad)
    wc["advanced_to_knockout"] = wc["Team"].isin(ADVANCED_TEAMS)

    wc = wc.rename(columns={
        "Date": "date", "Round": "round", "Opponent": "opponent",
        "Min": "minutes", "SoTA": "shots_on_target_against",
        "GA": "goals_against", "Saves": "saves", "Save%": "save_pct",
    })

    keep = ["date", "round", "Player", "Team", "opponent", "minutes",
            "shots_on_target_against", "goals_against", "saves", "save_pct",
            "advanced_to_knockout"]
    return wc[[c for c in keep if c in wc.columns]]


def main():
    if not MANIFEST_PATH.exists():
        raise SystemExit(
            f"{MANIFEST_PATH} not found -- run scrape_gk_stats.py first."
        )

    manifest = json.loads(MANIFEST_PATH.read_text())
    ok_entries = [m for m in manifest if m["status"] == "ok"]
    print(f"{len(ok_entries)}/{len(manifest)} goalkeepers were successfully scraped.")

    frames = []
    for entry in ok_entries:
        html_path = Path(entry["raw_path"])
        df = parse_goalkeeper_page(html_path, entry["name"])
        if not df.empty:
            frames.append(df)

    if not frames:
        raise SystemExit(
            "No goalkeeper-match rows were parsed from any scraped page. "
            "Something is wrong upstream (blocked pages, changed table "
            "structure, etc.) -- do not fall back to silently reusing the "
            "old manually-collected data/gk_match.csv without saying so."
        )

    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(combined)} rows to {OUTPUT_PATH}")
    print(f"Unique goalkeepers represented: {combined['Player'].nunique()}")


if __name__ == "__main__":
    main()
