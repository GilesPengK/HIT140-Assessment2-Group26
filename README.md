# HIT140 Assessment 2 — Darwin Group 26

FIFA World Cup 2026 analysis. Four analytic tasks, one per member.

| Member | Task | Notebook |
|---|---|---|
| Sihao Cui | Discipline — fouls, group stage vs knockout | `notebooks/task_discipline_sihao.ipynb` |
| Peng Song | 'Possession — UEFA teams vs 50% | notebooks/task_possession_peng.ipynb' |
| Luke Ren | Chance creation — assists per 90, MF vs FW | notebooks/task_assists_luke.ipynb* |
| Abel Qin | Goalkeeping — save percentage | `notebooks/task_gk_yadong.ipynb` |

Due **10 September 2026, 14:00 ACST**.

---

## Setup

The unit's working environment is the conda env `test06` (Python 3.10.14).
The `base` env is broken — NumPy 2.x against a NumPy 1.x scipy/matplotlib, and
no pandas at all — so do not use it.

```bash
conda activate test06
pip install -r requirements.txt

# only needed to re-scrape the match pages
playwright install chromium
```

---

## Pipeline

Run in order from the project root. Each step writes to disk, so a later step
never forces you to redo an earlier one.

```bash
python src/fetch_metadata.py        # ~4 min   API, no browser
python src/scrape_match_stats.py    # ~10 min  browser, 104 pages
python src/build_dataset.py         # seconds  parse -> team_match.csv
```

| Step | What it does | Output |
|---|---|---|
| `fetch_metadata.py` | Calls `api.fifa.com/api/v3/live/football/{id}` for all 104 matches. Stage, group, date, venue, attendance, referee, score, cards, squads. | `data/raw/match_meta.json`, `data/clean/match_meta.csv` |
| `scrape_match_stats.py` | Loads each match page in Chromium, scrolls to force the lazy-loaded stats to mount, saves the rendered text. Skips matches already downloaded, so it is safe to re-run after an interruption. | `data/raw/pages/*.txt` (104 files) |
| `build_dataset.py` | Parses the saved pages, joins the metadata, writes the shared dataset. | `data/clean/team_match.csv` |

### Why a browser is needed for step 2

Possession, fouls, passes and the rest are rendered client-side and there is no
public JSON endpoint for them. Checked and ruled out:

- `api.fifa.com/api/v3/live/football/{id}` — returns `BallPossession: null`
- `api.fifa.com/api/v3/statistics/{comp}/{season}/{stage}/{match}` — 404
- The CloudFront path used by the page only serves `status.json`

Step 1 is deliberately kept browser-free so the metadata can be refreshed
cheaply on its own.

### Two obstacles the scraper works around

**The bot-detection script crashes headless Chromium.** fifa.com serves an
Akamai sensor script from an obfuscated same-origin path with no file
extension. With a CDP client attached it kills the browser process with
`SIGTRAP` a few seconds into the page load — the failure looks like
`TargetClosedError`, which reads as a timeout and sends you looking in the
wrong place. Aborting that single request fixes it, and the statistics still
render because they are fetched separately.

**The stats mount lazily on scroll.** The scraper scrolls to the bottom and
re-reads until the `FIFA Official Stats` marker appears, up to six rounds.

Both are worth a line in the presentation: they are concrete examples of
non-trivial data acquisition, and of alternatives explored before settling on
an approach.

---

## `team_match.csv`

One row per team per match: **104 matches x 2 = 208 rows**.

| Column | Meaning |
|---|---|
| `match_id` | FIFA match id, 400021440–400021543 |
| `stage_id` | `289273` is the group stage; every other value is knockout |
| `stage_name` | Group stage / Round of 32 / … / Final |
| `is_group_stage` | boolean, the grouping variable for the discipline task |
| `group_name` | Group A–L, null for knockout matches |
| `date_utc`, `attendance`, `referee` | match context |
| `side` | `home` / `away` |
| `team`, `opponent` | team names |
| `score`, `opponent_score` | final score |
| `possession_pct` | possession % for this team |
| `possession_contested_pct` | FIFA reports possession in three parts; this is the contested share, identical for both rows of a match |
| `fouls` | FIFA's "Fouls Against" — fouls this team committed |
| `yellow_cards`, `red_cards`, `offsides` | discipline |
| `shots`, `shots_on_target`, `corners` | attacking |
| `passes`, `passes_completed` | distribution |
| *(further columns)* | the remaining FIFA panels, prefixed by section name |

Column names are fixed. Changing one breaks four people's notebooks.

### Stage breakdown (verified against the fixtures page)

| Stage | Matches | Team-match rows |
|---|---|---|
| Group stage | 72 | 144 |
| Round of 32 | 16 | 32 |
| Round of 16 | 8 | 16 |
| Quarter-final | 4 | 8 |
| Semi-final | 2 | 4 |
| Third place play-off | 1 | 2 |
| Final | 1 | 2 |
| **Total** | **104** | **208** |

---

## Data sources

| Source | Used for | Notes |
|---|---|---|
| `api.fifa.com/api/v3` | match metadata | Open JSON, no auth |
| `fifa.com/en/match-centre` | per-match team stats | Client-rendered |
| `fifa.com/…/statistics/player-statistics` | player and goalkeeper totals | **Paginates 50 rows at a time and defaults to sorting by goals — click "Load more" until it disappears before copying, or the sample is biased toward top scorers** |
| FBref | *not used* | Cloudflare bot protection |

Requests are rate-limited (`REQUEST_DELAY` / `PAGE_DELAY` in `src/config.py`).
Please leave the delays in.

---

## Layout

```
project/
├── src/
│   ├── config.py               match index, stage map, URLs, delays
│   ├── fetch_metadata.py       step 1
│   ├── scrape_match_stats.py   step 2
│   └── build_dataset.py        step 3 + the page parser
├── tests/
│   └── fixture_400021443.txt   real captured page text, used to test the parser
├── notebooks/
├── meeting-minutes/            minutes posted to the Teams channel
├── data/raw/                   scraped pages + raw JSON, never edited by hand
├── data/clean/                 generated CSVs
└── figures/                    plots saved by the notebooks
```

The raw data is committed on purpose — the assessment asks for "all Python
files and the datasets used", so the repository has to be self-contained.

## Testing the parser

`tests/fixture_400021443.txt` is the real rendered text of Mexico 2–0 South
Africa, captured on 2026-08-16. Parsing it should recover 42 statistics,
including `possession_pct` 57/36 and `fouls` 12/11.

```bash
python -c "import sys; sys.path.insert(0,'src'); from build_dataset import parse_page; \
r = parse_page(open('tests/fixture_400021443.txt').read()); \
print(r['home']['possession_pct'], r['away']['Discipline: Fouls Against'])"
# -> 57.0 11.0
```
