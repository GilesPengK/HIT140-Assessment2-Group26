"""Step 1 — pull match metadata from the FIFA JSON API.

No browser needed: api.fifa.com/api/v3/live/football/{match_id} returns a
~35 KB JSON document per match. This gives us stage, group, date, venue,
attendance, referee, score, cards and squads.

It does NOT give possession / fouls / passes — those live only in the
rendered match page, which is what scrape_match_stats.py handles.

Run:  python src/fetch_metadata.py
Out:  data/raw/match_meta.json   (one record per match, all 104)
      data/clean/match_meta.csv
"""

import json
import time

import pandas as pd
import requests

from config import MATCH_INDEX, RAW, CLEAN, REQUEST_DELAY, USER_AGENT, api_url


def _first_desc(node):
    """FIFA wraps localised strings as [{'Locale': 'en-GB', 'Description': '...'}]."""
    if isinstance(node, list) and node:
        return node[0].get("Description")
    return None


def parse_match(payload, stage_id, stage_name, is_group):
    home = payload.get("HomeTeam") or {}
    away = payload.get("AwayTeam") or {}

    officials = payload.get("Officials") or []
    referee = next(
        (_first_desc(o.get("NameShort")) for o in officials if o.get("OfficialType") == 1),
        None,
    )

    return {
        "match_id": payload.get("IdMatch"),
        "match_number": payload.get("MatchNumber"),
        "stage_id": stage_id,
        "stage_name": stage_name,
        "is_group_stage": is_group,
        "group_name": _first_desc(payload.get("GroupName")),
        "date_utc": payload.get("Date"),
        "stadium": _first_desc((payload.get("Stadium") or {}).get("Name")),
        "attendance": payload.get("Attendance"),
        "referee": referee,
        "home_team": _first_desc(home.get("TeamName")),
        "away_team": _first_desc(away.get("TeamName")),
        "home_abbr": _first_desc(home.get("Abbreviation")),
        "away_abbr": _first_desc(away.get("Abbreviation")),
        "home_score": home.get("Score"),
        "away_score": away.get("Score"),
        "home_bookings": len(home.get("Bookings") or []),
        "away_bookings": len(away.get("Bookings") or []),
    }


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    raw_records, rows, failures = [], [], []

    for i, (stage_id, stage_name, is_group, match_id) in enumerate(MATCH_INDEX, 1):
        try:
            resp = session.get(api_url(match_id), timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # network hiccup, bad JSON, 404 …
            failures.append({"match_id": match_id, "error": repr(exc)})
            print(f"[{i:3d}/104] {match_id}  FAILED  {exc}")
            time.sleep(REQUEST_DELAY)
            continue

        raw_records.append(payload)
        row = parse_match(payload, stage_id, stage_name, is_group)
        rows.append(row)
        print(
            f"[{i:3d}/104] {match_id}  {row['home_team']} {row['home_score']}"
            f"-{row['away_score']} {row['away_team']}  ({stage_name})"
        )
        time.sleep(REQUEST_DELAY)

    (RAW / "match_meta.json").write_text(
        json.dumps(raw_records, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    df = pd.DataFrame(rows)
    df.to_csv(CLEAN / "match_meta.csv", index=False)

    print(f"\nSaved {len(df)} matches to {CLEAN / 'match_meta.csv'}")
    if failures:
        print(f"{len(failures)} failures — rerun to pick them up:")
        for f in failures:
            print("  ", f)
    else:
        print("No failures.")

    print("\nMatches per stage:")
    print(df.groupby("stage_name", sort=False).size().to_string())


if __name__ == "__main__":
    main()
