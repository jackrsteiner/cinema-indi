# movindi — agent instructions

This repo is a static GitHub Pages site listing films. The single source of
truth is `list.md`. A GitHub Action fetches everything else.

## "Add X to the movindi list"

1. Resolve the film to its canonical English title (the one IMDb/OMDb uses, e.g.
   "WarGames", "Ferris Bueller's Day Off", "My Neighbor Totoro"). A series or
   trilogy becomes one line per film.
2. Insert it into `list.md` on its own line, in alphabetical order **ignoring a
   leading "The", "A" or "An"**. Plain text, no bullets, no other fields.
3. If a title is ambiguous (remakes, same-name films), append the year:
   `True Grit (2010)`.
4. A TV series is marked `(series)`, with the first-air year if ambiguous:
   `Bluey (series)`, `Fargo (2014 series)`. Without the marker the lookup is
   film-only. One line per series, never per season or episode.
5. For a franchise entry use the full IMDb title so the films sort next to
   each other: `Indiana Jones and the Raiders of the Lost Ark`,
   `Star Wars: Episode IV - A New Hope`, `Terminator 2: Judgment Day`. No
   franchise tags or badges.
6. Run `python -m unittest discover -s tests` (no network needed), commit with a
   message like `Add The Iron Giant`, and push to `main`. Do not edit
   `data/films.json`; the Action fills it in and commits it back.

## "Mark X as watched" / "We watched X on Saturday"

Add a line to `watched.md` containing the film's exact `list.md` line, followed
by the date as `YYYY-MM-DD` when one is known (resolve relative dates against
today). One line per film; remove the line to un-mark it. The site shows a
"Watched" chip and offers Unwatched / Watched toggles. Run the tests (they check every
`watched.md` line matches a `list.md` line), commit, push to `main`.

## Removing / renaming

Delete or change the line in `list.md`. The Action drops the stale cache entry.
Rename the matching key in `data/overrides.json` and the line in `watched.md`
if they exist.

## Fixing bad data

Put corrections in `data/overrides.json` keyed by the `list.md` line
(`imdb_id`, `title`, `year`, `rated`, `synopsis`, `poster`, `runtime_min`,
`total_seasons`, `age`). Never hand-edit `data/films.json`.

## Ages

Two files decide the age shown on a card:

- `data/labels.json`: ages the user has set by hand, keyed by the exact
  `list.md` line. These win. When the user says "X should be 8" or gives a
  batch of ages, add or change entries here (integers), never in
  `films.json`. Keys must match `list.md` lines; the tests check this.
- `data/age-rules.json`: the fitted model that scores everything else. Its
  coefficients were fitted to `labels.json`; do not hand-edit them or invent
  ages. Refitting is a separate task the user asks for explicitly.

Run `python scripts/build.py --explain` to see the resulting table, with
labelled titles marked.

## Layout

- `scripts/movindi.py` shared helpers (list parsing, sort keys, age formula)
- `scripts/enrich.py` OMDb + IMDb GraphQL + TMDB fetching → `data/films.json`
- `scripts/build.py` → `_site/` (static HTML/JS + `films.json`)
- `site/` the page source
- `.github/workflows/build.yml` enrich → commit data → build → deploy Pages
