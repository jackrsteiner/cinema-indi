# movindi

A list of films I want to share with my son, published at
**https://jackrsteiner.github.io/movindi/**.

The whole thing is driven by one file: [`list.md`](list.md), a plain alphabetical
list of titles. Everything else (year, poster, synopsis, IMDb link, age) is fetched
automatically by a GitHub Action and rendered as a static page.

## Adding a film

1. Add the title on its own line in `list.md`, in alphabetical order **ignoring a
   leading "The", "A" or "An"** (so *The Graduate* sorts under G).
2. If the title is ambiguous, add the year in parentheses: `True Grit (2010)`.
3. Commit to `main`. The Action looks the film up, updates `data/films.json`,
   rebuilds the site and deploys it. Takes a minute or two.

Or just tell an agent "Add *Title* to the movindi list"; `CLAUDE.md` tells it how.

## How the page works

- **A–Z** groups by first letter of the title with articles stripped.
- **Year** groups by release year.
- **Age** groups by a computed minimum age (see below).

Each view has a sticky jump bar to any letter / year / age.

## Age appropriateness

Deterministic and reproducible: no human or AI judgement is involved, only data
plus the rules in [`data/age-rules.json`](data/age-rules.json).

```
age = max( rating_floor[MPAA rating],
           category_floor[category][severity]  for each Parents Guide category )
      + stacking bumps
```

- **MPAA rating** comes from OMDb (falls back to IMDb's certificate).
- **Parents Guide severities** (None / Mild / Moderate / Severe for Sex & Nudity,
  Violence & Gore, Profanity, Alcohol/Drugs/Smoking, Frightening & Intense Scenes)
  come from IMDb. Each is the median of IMDb user votes, and the Action re-fetches
  them monthly because they drift.
- Every number in the formula lives in `age-rules.json`. Change a number, push,
  and the site regroups; nothing needs to be refetched.
- Each card shows the five severities as coloured dots and the rule(s) that set
  its age, so you can see *why* a film landed where it did.
- The build step prints the full age table into the workflow run summary.

To pin a film's age by hand, set `"age"` for it in `data/overrides.json`.

## Data files

| File | Who edits it | Purpose |
|---|---|---|
| `list.md` | you / an agent | the list |
| `data/overrides.json` | you / an agent | manual fixes keyed by the `list.md` line: `imdb_id`, `title`, `year`, `rated`, `synopsis`, `poster`, `series`, `series_order`, `age` |
| `data/age-rules.json` | you | the age formula |
| `data/films.json` | the Action | cache of fetched data (committed back automatically) |

## One-time setup

1. **Secrets** (repo → Settings → Secrets and variables → Actions):
   - `OMDB_API_KEY` — free key from https://www.omdbapi.com/apikey.aspx (required).
   - `TMDB_API_KEY` — free key from https://www.themoviedb.org/settings/api
     (optional; posters are hotlinked from TMDB when present, otherwise the OMDb
     poster URL is used).
2. **Pages** (repo → Settings → Pages): set *Source* to **GitHub Actions**.
3. Run the *Build and deploy* workflow once from the Actions tab (or push to `main`).

## Running locally

```
OMDB_API_KEY=... python scripts/enrich.py   # fetch missing films into data/films.json
python scripts/build.py --explain           # build _site/ and print the age table
python -m http.server -d _site 8000         # open http://localhost:8000
python -m unittest discover -s tests        # tests (no network)
```
