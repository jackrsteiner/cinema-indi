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
   A TV series gets `(series)`, or `(2014 series)` if the year is needed too.
   Anything without the marker is looked up as a film.
3. Commit to `main`. The Action looks the film up, updates `data/films.json`,
   rebuilds the site and deploys it. Takes a minute or two.

Or just tell an agent "Add *Title* to the movindi list"; `CLAUDE.md` tells it how.

The site also serves the list as a bare page at
[`/list.html`](https://jackrsteiner.github.io/movindi/list.html) (titles only,
watched ones marked) and the raw file at `/list.md`, for a quick "is it on the
list already?" check. Each page links to the other.

## Marking a film watched

Add its `list.md` line to [`watched.md`](watched.md), optionally followed by a
date:

```
The Princess Bride 2026-09-01
True Grit (2010)
```

The page shows a "Watched" chip with the date and has an All / Unwatched / Watched
filter. Or tell an agent "mark *Title* as watched".

## How the page works

- **A–Z** groups by first letter of the title with articles stripped.
- **Year** groups by release year.
- **Age** groups by a computed minimum age (see below).

Each view has a sticky jump bar to any letter / year / age. Cards show the
runtime (per-episode average and season count for a series) and a "Series"
chip; films carry no chip. Each card shows the
five IMDb Parents Guide categories as icons (💋 sex & nudity, 💥 violence,
🤬 profanity, 🍺 alcohol/drugs, 👻 frightening scenes) coloured by severity.

## Age appropriateness

Two layers, both plain data in the repo:

1. **Your labels** in [`data/labels.json`](data/labels.json): ages you have set
   by hand, keyed by the `list.md` line. A labelled title always shows its
   label (the tooltip says so).
2. **A fitted model** in [`data/age-rules.json`](data/age-rules.json) for
   everything else:

```
age = round( intercept
           + Σ category_weight × severity score      (IMDb Parents Guide, None=0 … Severe=3)
           + rating_offset[rating]                    (TV ratings mapped to MPAA via rating_aliases)
           + kind_offset (series)
           + Σ genre_offset[genre]                    (OMDb genres)
           + numeric terms: IMDb rating, runtime (films only), … )
      clamped to [min_age, max_age]
```

The coefficients are fitted to the labels, and the feature set is chosen by
leave-one-out error (how well each label is predicted from the others), because
the model's only job is the unlabelled titles. Some labels are unreachable by
any formula over these inputs (Jurassic Park at 13 and Last Crusade at 5 have
near-identical Parents Guides), which is why labels are authoritative rather
than targets the model must hit.

To recalibrate: add labels, refit (a scratch least-squares fitter; any
regression over these features works), paste the coefficients into
`age-rules.json`, push. Hover an age chip to see its terms; `python
scripts/build.py --explain` prints the whole table with labelled titles marked.
`data/overrides.json` can also pin an `"age"` for a single title.

A title IMDb has no Parents Guide for (shorts, obscure titles) is still scored
from its other inputs with the missing severities set to `missing_severity`
(default 0, i.e. None). Its chip is dashed with a ~ and the tooltip says which
categories were assumed.

Note on IMDb: severities come from the same GraphQL endpoint IMDb's own site
uses. It is undocumented, refuses schema introspection, and its responses
carry a disclaimer limiting use to limited non-commercial purposes. A personal
list for one family fits that, but keep the data in this repo, not on a public
API of your own.

## Data files

| File | Who edits it | Purpose |
|---|---|---|
| `list.md` | you / an agent | the list |
| `watched.md` | you / an agent | which films you have watched, with optional dates |
| `data/overrides.json` | you / an agent | manual fixes keyed by the `list.md` line: `imdb_id`, `title`, `year`, `rated`, `synopsis`, `poster`, `series`, `series_order`, `age` |
| `data/labels.json` | you / an agent | hand-set ages, authoritative, and the model's training set |
| `data/age-rules.json` | the fitter | the model for unlabelled titles |
| `data/films.json` | the Action | cache of fetched data (committed back automatically) |

## One-time setup

1. **Secrets** (repo → Settings → Secrets and variables → Actions):
   - `OMDB_API_KEY` — free key from https://www.omdbapi.com/apikey.aspx (required).
   - `TMDB_API_KEY` — free key from https://www.themoviedb.org/settings/api
     (optional; posters are hotlinked from TMDB when present, otherwise the OMDb
     poster URL is used).
2. **Pages** (repo → Settings → Pages): set *Source* to **GitHub Actions**.
3. Run the *Build and deploy* workflow once from the Actions tab (or push to `main`).

If every film shows "Lookup failed" with HTTP 401, the OMDb key has not been
activated yet: click the link in OMDb's confirmation email, then re-run the
workflow. You can sanity-check a key with
`https://www.omdbapi.com/?apikey=YOUR_KEY&t=WarGames`.

## Running locally

```
OMDB_API_KEY=... python scripts/enrich.py   # fetch missing films into data/films.json
python scripts/build.py --explain           # build _site/ and print the age table
python -m http.server -d _site 8000         # open http://localhost:8000
python -m unittest discover -s tests        # tests (no network)
```
