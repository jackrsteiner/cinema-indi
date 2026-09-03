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

## Marking a film watched

Add its `list.md` line to [`watched.md`](watched.md), optionally followed by a
date:

```
The Princess Bride 2026-09-01
True Grit (2010)
```

The page shows a ✓ badge with the date and has an All / Unwatched / Watched
filter. Or tell an agent "mark *Title* as watched".

## How the page works

- **A–Z** groups by first letter of the title with articles stripped.
- **Year** groups by release year.
- **Age** groups by a computed minimum age (see below).

Each view has a sticky jump bar to any letter / year / age. Each card shows the
five IMDb Parents Guide categories as icons (💋 sex & nudity, 💥 violence,
🤬 profanity, 🍺 alcohol/drugs, 👻 frightening scenes) coloured by severity.

## Age appropriateness

Deterministic and reproducible: no human or AI judgement at build time, only
data plus the coefficients in [`data/age-rules.json`](data/age-rules.json).

```
age = round( intercept
           + Σ category_weight × severity score      (IMDb Parents Guide, None=0 … Severe=3)
           + rating_offset[MPAA rating]
           + Σ genre_offset[genre]                    (OMDb genres)
           + runtime and IMDb-rating terms )
      clamped to [min_age, max_age], then raised to rating_floor[rating] if lower
```

The coefficients were **fitted to hand-labelled ages** for 21 films (3: Totoro,
Ponyo, Prince Achmed; 4: Kiki, Penzance, Chipmunk Adventure, Up, Iron Giant,
WALL-E, Muppet Treasure Island; 5: Princess Bride, Star Wars, Land Before Time,
Back to the Future, Raiders, Last Crusade, WarGames; 6: Empire, Real Genius,
Return of the Jedi; 7: Temple of Doom). The fit reproduces 20 of them; Raiders
comes out one year high because its data is identical to Last Crusade's.
Nothing R-rated has been labelled yet, so `rating_floor` pins R at 12 until it is.

A film IMDb has no Parents Guide for (shorts, obscure titles) is still scored
from its other inputs, with the missing severities set to `missing_severity`
(default 0, i.e. None). Its age chip is drawn dashed with a ~ to mark it as an
estimate, and the tooltip says which categories were assumed.

To recalibrate: label more films, refit (a scratch fitter lives outside the
repo; any least-squares fit to these features works), paste the coefficients
into `age-rules.json`, push. Each card shows its terms so you can see why a
film landed where it did, and `python scripts/build.py --explain` prints the
whole table. To pin a film by hand, set `"age"` for it in `data/overrides.json`.

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
