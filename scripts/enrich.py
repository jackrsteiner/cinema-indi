#!/usr/bin/env python3
"""Fill in data/films.json from list.md using OMDb (metadata), IMDb's GraphQL
endpoint (Parents Guide severities + certificate) and TMDB (poster path).

Usage:
    OMDB_API_KEY=... [TMDB_API_KEY=...] python scripts/enrich.py [--refresh] [--max-age-days N]

Only titles missing from the cache are looked up on OMDb; Parents Guide data is
re-fetched when older than --max-age-days (default 30) because severities are
vote-based and drift over time. Failures are recorded per film, never fatal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from movindi import (  # noqa: E402
    CATEGORY_KEYS, FILMS_PATH, LIST_PATH, OVERRIDES_PATH, check_list_sorted,
    load_json, parse_list, save_json,
)

OMDB_URL = "https://www.omdbapi.com/"
IMDB_GRAPHQL_URL = "https://api.graphql.imdb.com/"
TMDB_FIND_URL = "https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
USER_AGENT = "movindi/1.0 (+https://github.com/jackrsteiner/movindi)"

PARENTS_GUIDE_QUERY = """
query ParentsGuide($id: ID!) {
  title(id: $id) {
    id
    certificate { rating }
    parentsGuide {
      categories {
        category { id text }
        severity { id text }
      }
    }
  }
}
"""


def http_json(url: str, data: dict | None = None, headers: dict | None = None, retries: int = 3):
    """GET (or POST json when data is given) and parse JSON, with backoff retries."""
    body = json.dumps(data).encode("utf-8") if data is not None else None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"request failed after {retries} attempts: {url}: {last_err}")


# --------------------------------------------------------------------------
# Fetchers. Each takes `fetch` (an http_json-compatible callable) so tests can
# substitute canned responses.
# --------------------------------------------------------------------------

def omdb_lookup(entry: dict, api_key: str, imdb_id: str | None = None, fetch=http_json) -> dict:
    """Resolve a list entry to an OMDb record. Raises on no match."""
    def call(params: dict) -> dict:
        params = {"apikey": api_key, "plot": "short", **params}
        return fetch(OMDB_URL + "?" + urllib.parse.urlencode(params))

    if imdb_id:
        rec = call({"i": imdb_id})
    else:
        params = {"t": entry["title"], "type": "movie"}
        if entry.get("year"):
            params["y"] = str(entry["year"])
        rec = call(params)
        if rec.get("Response") != "True":
            # Fall back to a search and take the first movie hit.
            sparams = {"s": entry["title"], "type": "movie"}
            if entry.get("year"):
                sparams["y"] = str(entry["year"])
            search = call(sparams)
            hits = [h for h in search.get("Search", []) if h.get("imdbID")]
            if not hits:
                raise RuntimeError(f"OMDb: no match for {entry['key']!r} ({search.get('Error', 'no results')})")
            rec = call({"i": hits[0]["imdbID"]})
    if rec.get("Response") != "True":
        raise RuntimeError(f"OMDb: {rec.get('Error', 'unknown error')} for {entry['key']!r}")

    year_str = (rec.get("Year") or "").split("–")[0].strip()
    return {
        "imdb_id": rec["imdbID"],
        "title": rec.get("Title") or entry["title"],
        "year": int(year_str) if year_str.isdigit() else entry.get("year"),
        "rated": _clean(rec.get("Rated")),
        "plot": _clean(rec.get("Plot")),
        "omdb_poster": _clean(rec.get("Poster")),
        "omdb_fetched_at": _now(),
    }


def imdb_parents_guide(imdb_id: str, fetch=http_json) -> dict:
    """Return {'parents_guide': {key: severity}, 'imdb_certificate': str|None}."""
    payload = {"query": PARENTS_GUIDE_QUERY, "variables": {"id": imdb_id}}
    resp = fetch(IMDB_GRAPHQL_URL, data=payload, headers={"x-imdb-client-name": "imdb-web-next"})
    title = (resp.get("data") or {}).get("title") or {}
    if not title:
        raise RuntimeError(f"IMDb GraphQL: no title data for {imdb_id}: {resp.get('errors')}")
    guide = {}
    for cat in ((title.get("parentsGuide") or {}).get("categories") or []):
        key = _category_key(cat.get("category") or {})
        sev = (cat.get("severity") or {})
        sev_text = sev.get("text") or (sev.get("id") or "").title()
        if key and sev_text:
            guide[key] = sev_text
    cert = (title.get("certificate") or {}).get("rating")
    return {"parents_guide": guide, "imdb_certificate": cert, "guide_fetched_at": _now()}


def tmdb_poster(imdb_id: str, api_key: str, fetch=http_json) -> str | None:
    url = TMDB_FIND_URL.format(imdb_id=imdb_id) + "&api_key=" + urllib.parse.quote(api_key)
    resp = fetch(url)
    hits = resp.get("movie_results") or resp.get("tv_results") or []
    path = hits[0].get("poster_path") if hits else None
    return f"https://image.tmdb.org/t/p/w342{path}" if path else None


def _category_key(category: dict) -> str | None:
    cid = (category.get("id") or "").upper()
    if cid in CATEGORY_KEYS:
        return CATEGORY_KEYS[cid]
    text = (category.get("text") or "").lower()
    for needle, key in (("nudity", "sex"), ("violence", "violence"), ("profanity", "profanity"),
                        ("alcohol", "drugs"), ("drug", "drugs"), ("frightening", "frightening")):
        if needle in text:
            return key
    return None


def _clean(v):
    return None if v in (None, "", "N/A") else v


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _older_than(stamp: str | None, days: int) -> bool:
    if not stamp:
        return True
    try:
        t = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - t > timedelta(days=days)


# --------------------------------------------------------------------------

def enrich(entries, cache, overrides, *, omdb_key, tmdb_key=None, refresh=False,
           max_age_days=30, fetch=http_json, log=print) -> dict:
    """Return the updated cache dict. Pure apart from `fetch` and `log`."""
    out = {}
    for entry in entries:
        key = entry["key"]
        rec = dict(cache.get(key, {}))
        ov = overrides.get(key, {})
        rec["list_title"] = entry["title"]
        rec.pop("error", None)
        try:
            if refresh or not rec.get("imdb_id"):
                if not omdb_key:
                    raise RuntimeError("OMDB_API_KEY is not set")
                rec.update(omdb_lookup(entry, omdb_key, imdb_id=ov.get("imdb_id"), fetch=fetch))
                log(f"  OMDb    {key} -> {rec['imdb_id']} ({rec.get('title')}, {rec.get('year')})")
            if refresh or _older_than(rec.get("guide_fetched_at"), max_age_days):
                try:
                    rec.update(imdb_parents_guide(rec["imdb_id"], fetch=fetch))
                    log(f"  Guide   {key} -> {rec.get('parents_guide')}")
                except Exception as e:  # keep metadata even if the guide fails
                    rec["guide_error"] = str(e)
                    log(f"  Guide   {key} FAILED: {e}")
            if tmdb_key and (refresh or "tmdb_poster" not in rec):
                try:
                    rec["tmdb_poster"] = tmdb_poster(rec["imdb_id"], tmdb_key, fetch=fetch)
                    log(f"  TMDB    {key} -> {rec['tmdb_poster']}")
                except Exception as e:
                    log(f"  TMDB    {key} FAILED: {e}")
        except Exception as e:
            rec["error"] = str(e)
            log(f"  ERROR   {key}: {e}")
        out[key] = rec
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-fetch everything, ignoring the cache")
    ap.add_argument("--max-age-days", type=int, default=30, help="re-fetch Parents Guide data older than this")
    args = ap.parse_args(argv)

    entries = parse_list(LIST_PATH.read_text(encoding="utf-8"))
    problems = check_list_sorted(entries)
    for p in problems:
        print(f"WARNING list.md: {p}")

    cache = load_json(FILMS_PATH, {})
    overrides = {k: v for k, v in load_json(OVERRIDES_PATH, {}).items() if not k.startswith("_")}
    print(f"{len(entries)} titles in list.md, {len(cache)} cached")
    updated = enrich(entries, cache, overrides,
                     omdb_key=os.environ.get("OMDB_API_KEY", ""),
                     tmdb_key=os.environ.get("TMDB_API_KEY") or None,
                     refresh=args.refresh, max_age_days=args.max_age_days)
    save_json(FILMS_PATH, updated)

    errors = {k: v["error"] for k, v in updated.items() if v.get("error")}
    guide_errors = {k: v["guide_error"] for k, v in updated.items() if v.get("guide_error")}
    summary = [f"# movindi enrich", f"- {len(entries)} titles, {len(errors)} unresolved, {len(guide_errors)} without Parents Guide"]
    summary += [f"- ⚠️ list.md: {p}" for p in problems]
    summary += [f"- ❌ **{k}**: {v}" for k, v in errors.items()]
    summary += [f"- ⚠️ **{k}** (Parents Guide): {v}" for k, v in guide_errors.items()]
    print("\n".join(summary))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
