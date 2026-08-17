"""Step 3 — turn the scraped pages plus the API metadata into team_match.csv.

Output shape: one row per team per match, so 104 matches x 2 = 208 rows.
That is the grain all four analytic tasks were designed around, and it is
also the grain Assessment 3's second regression model needs.

The stats block on a FIFA match page reads as a flat run of lines:

    Discipline
    Yellow Cards
    1          <- home
    2          <- away
    Fouls Against
    12
    11

so the parser walks the lines, tracks which section header it last saw, and
reads two values after each known label. Possession is the one exception: it
carries three values (home %, away %, "% in contest").

Labels like "Total" appear under more than one section, which is why the
section name is kept as part of the column name.

Run:  python src/build_dataset.py
In:   data/raw/pages/*.txt, data/clean/match_meta.csv
Out:  data/clean/team_match.csv
"""

import re

import pandas as pd

from config import RAW, CLEAN

PAGES = RAW / "pages"
MARKER = "FIFA Official Stats"

# Section header -> labels that follow it, in page order.
SECTIONS = {
    "Goal": ["Total", "Conceded", "Inside the Penalty Area",
             "Outside the Penalty Area", "Assists"],
    "Attempts at Goal": ["Total", "On Target", "Off Target",
                         "Inside the Penalty Area", "Outside the Penalty Area"],
    "Final Third Entries": ["Left Channel", "Left Inside Channel", "Central Channel",
                            "Right Inside Channel", "Right Channel"],
    "Offers to Receive": ["Total", "In Behind", "In Between", "In Front",
                          "Receptions Between Midfield and Defensive Lines",
                          "Receptions Behind the Defensive Line"],
    "Line Breaks": ["Attempted Line Breaks", "Completed Line Breaks",
                    "Attempted Defensive Line Breaks", "Completed Defensive Line Breaks"],
    "Discipline": ["Yellow Cards", "Red Cards", "Fouls Against", "Offsides"],
    "Distribution": ["Passes", "Passes Completed", "Crosses", "Crosses Completed",
                     "Switches of Play Completed"],
    "Set Plays": ["Corners", "Free Kicks", "Penalties Scored"],
    "Defending": ["Own Goals", "Forced Turnovers", "Pressing Applied"],
}

# The handful of columns the four analytic tasks actually need, given short
# names so nobody has to type "Discipline: Fouls Against" in their notebook.
RENAME = {
    "possession_pct": "possession_pct",
    "Discipline: Fouls Against": "fouls",
    "Discipline: Yellow Cards": "yellow_cards",
    "Discipline: Red Cards": "red_cards",
    "Discipline: Offsides": "offsides",
    "Distribution: Passes": "passes",
    "Distribution: Passes Completed": "passes_completed",
    "Attempts at Goal: Total": "shots",
    "Attempts at Goal: On Target": "shots_on_target",
    "Set Plays: Corners": "corners",
    "Goal: Total": "goals_for",
    "Goal: Conceded": "goals_against",
    "Goal: Assists": "assists",
}

NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def _clean_num(s):
    s = s.strip().rstrip("%").strip()
    return float(s) if NUM.match(s) else None


def parse_page(text):
    """Return {'home': {...}, 'away': {...}} of stat -> value, or None."""
    if MARKER not in text:
        return None

    lines = [ln.strip() for ln in text[text.index(MARKER):].split("\n")]
    lines = [ln for ln in lines if ln]

    home, away = {}, {}
    section = None
    i = 0

    while i < len(lines):
        line = lines[i]

        if line in SECTIONS:
            section = line
            i += 1
            continue

        if line == "Possession":
            vals = [_clean_num(x) for x in lines[i + 1:i + 3]]
            if all(v is not None for v in vals):
                home["possession_pct"], away["possession_pct"] = vals
                # lines[i+3] is "N% in contest" — one figure for the match
                contested = _clean_num(lines[i + 3].replace("in contest", ""))
                home["possession_contested_pct"] = contested
                away["possession_contested_pct"] = contested
                i += 4
                continue

        if section and line in SECTIONS[section]:
            vals = [_clean_num(x) for x in lines[i + 1:i + 3]]
            if all(v is not None for v in vals):
                key = f"{section}: {line}"
                home[key], away[key] = vals
                i += 3
                continue

        i += 1

    return {"home": home, "away": away} if home else None


def main():
    meta = pd.read_csv(CLEAN / "match_meta.csv")
    meta_by_id = meta.set_index("match_id").to_dict("index")

    rows, skipped = [], []

    for path in sorted(PAGES.glob("*.txt")):
        match_id = int(path.stem)
        parsed = parse_page(path.read_text(encoding="utf-8"))

        if parsed is None:
            skipped.append(match_id)
            continue

        m = meta_by_id.get(match_id)
        if m is None:
            skipped.append(match_id)
            continue

        for side in ("home", "away"):
            other = "away" if side == "home" else "home"
            row = {
                "match_id": match_id,
                "stage_id": m["stage_id"],
                "stage_name": m["stage_name"],
                "is_group_stage": m["is_group_stage"],
                "group_name": m["group_name"],
                "date_utc": m["date_utc"],
                "referee": m["referee"],
                "attendance": m["attendance"],
                "side": side,
                "team": m[f"{side}_team"],
                "opponent": m[f"{other}_team"],
                "score": m[f"{side}_score"],
                "opponent_score": m[f"{other}_score"],
            }
            row.update(parsed[side])
            rows.append(row)

    df = pd.DataFrame(rows)
    df = df.rename(columns=RENAME)

    # Put the columns the analyses use up front; keep everything else after.
    lead = ["match_id", "stage_id", "stage_name", "is_group_stage", "group_name",
            "date_utc", "referee", "attendance", "side", "team", "opponent",
            "score", "opponent_score", "possession_pct", "fouls",
            "yellow_cards", "red_cards", "shots", "shots_on_target", "passes",
            "passes_completed", "corners", "offsides"]
    ordered = [c for c in lead if c in df.columns]
    ordered += [c for c in df.columns if c not in ordered]
    df = df[ordered].sort_values(["match_id", "side"]).reset_index(drop=True)

    out = CLEAN / "team_match.csv"
    df.to_csv(out, index=False)

    print(f"Wrote {len(df)} rows x {df.shape[1]} columns to {out}")
    if len(df) != 208:
        print(f"  WARNING: expected 208 rows, got {len(df)}")
    if skipped:
        print(f"  {len(skipped)} matches skipped (no stats block): {skipped}")

    print("\nRows per stage:")
    print(df.groupby("stage_name", sort=False).size().to_string())
    print("\nMissing values in the key columns:")
    key = [c for c in ("possession_pct", "fouls", "yellow_cards", "passes") if c in df]
    print(df[key].isna().sum().to_string())


if __name__ == "__main__":
    main()
