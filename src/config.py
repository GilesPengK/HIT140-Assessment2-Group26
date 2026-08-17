"""Shared configuration for the HIT140 Assessment 2 data pipeline.

Match index verified against the FIFA fixtures page on 2026-08-16:
all 104 match IDs are consecutive from 400021440 to 400021543, and the
stage boundaries fall exactly where the tournament structure says they should.
That means we do not need to scrape the fixtures page at all.
"""

from pathlib import Path

# ---------------------------------------------------------------- paths

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
FIGURES = ROOT / "figures"

for _d in (RAW, CLEAN, FIGURES):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- tournament

COMPETITION_ID = 17
SEASON_ID = 285023

# stage_id -> (human readable name, is_group_stage, first_match_id, last_match_id)
STAGES = {
    289273: ("Group stage", True, 400021440, 400021511),   # 72 matches
    289287: ("Round of 32", False, 400021512, 400021527),  # 16
    289288: ("Round of 16", False, 400021528, 400021535),  # 8
    289289: ("Quarter-final", False, 400021536, 400021539),  # 4
    289290: ("Semi-final", False, 400021540, 400021541),   # 2
    289291: ("Third place play-off", False, 400021542, 400021542),
    289292: ("Final", False, 400021543, 400021543),
}


def match_index():
    """Yield (stage_id, stage_name, is_group_stage, match_id) for all 104 matches."""
    for stage_id, (name, is_group, lo, hi) in STAGES.items():
        for match_id in range(lo, hi + 1):
            yield stage_id, name, is_group, match_id


MATCH_INDEX = list(match_index())
assert len(MATCH_INDEX) == 104, f"expected 104 matches, built {len(MATCH_INDEX)}"

# ---------------------------------------------------------------- urls

API_MATCH = "https://api.fifa.com/api/v3/live/football/{match_id}?language=en"
PAGE_MATCH = (
    "https://www.fifa.com/en/match-centre/match/"
    "{comp}/{season}/{stage}/{match_id}"
)

# Be polite: the FIFA site is not ours. One request every REQUEST_DELAY seconds.
REQUEST_DELAY = 2.0
PAGE_DELAY = 3.0

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
    "(CDU HIT140 student project; contact via unit coordinator)"
)


def page_url(stage_id: int, match_id: int) -> str:
    return PAGE_MATCH.format(
        comp=COMPETITION_ID, season=SEASON_ID, stage=stage_id, match_id=match_id
    )


def api_url(match_id: int) -> str:
    return API_MATCH.format(match_id=match_id)
