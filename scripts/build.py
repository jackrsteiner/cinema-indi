#!/usr/bin/env python3
"""Build the static site into _site/ from list.md + data/*.json.

    python scripts/build.py            # writes _site/
    python scripts/build.py --explain  # also prints the age table

No network access. Age appropriateness is computed here from data/age-rules.json
so tweaking the rules only needs a rebuild, not a refetch.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from movindi import (  # noqa: E402
    CATEGORY_ICONS, CATEGORY_LABELS, FILMS_PATH, LABELS_PATH, LIST_PATH, OVERRIDES_PATH,
    ROOT, RULES_PATH, WATCHED_PATH, alpha_key, alpha_letter, compute_age, first_sentence,
    load_json, parse_list, parse_watched, sort_title,
)

SITE_SRC = ROOT / "site"
SITE_OUT = ROOT / "_site"


def build_records(entries, cache, overrides, rules, watched=None, labels=None) -> list[dict]:
    watched = watched or {}
    labels = labels or {}
    records = []
    for entry in entries:
        key = entry["key"]
        raw = dict(cache.get(key, {}))
        ov = overrides.get(key, {})
        # Overrides win over fetched values for the fields they name.
        for field in ("imdb_id", "title", "year", "rated", "runtime_min", "total_seasons"):
            if field in ov:
                raw[field] = ov[field]
        raw.setdefault("kind", entry.get("kind", "film"))
        if "synopsis" in ov:
            raw["plot"] = ov["synopsis"]

        title = raw.get("title") or entry["title"]
        age_info = compute_age(raw, rules)
        age_source = "model"
        if key in labels:
            age_info = {"age": labels[key], "reasons": ["Set by hand (data/labels.json)"], "unknown": False}
            age_source = "label"
        if "age" in ov:
            age_info = {"age": ov["age"], "reasons": ["Set manually in overrides.json"], "unknown": False}
            age_source = "override"
        poster = ov.get("poster") or raw.get("tmdb_poster") or raw.get("omdb_poster")
        imdb_id = raw.get("imdb_id")
        status = "error" if raw.get("error") else ("ok" if imdb_id else "pending")
        records.append({
            "key": key,
            "title": title,
            "sort_title": sort_title(title),
            "alpha_key": alpha_key(title),
            "letter": alpha_letter(title),
            "kind": raw.get("kind", "film"),
            "year": raw.get("year") or entry.get("year"),
            "year_label": year_label(raw, entry),
            "runtime_label": runtime_label(raw),
            "rated": raw.get("rated") or raw.get("imdb_certificate"),
            "synopsis": first_sentence(raw.get("plot")),
            "poster": poster,
            "imdb_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None,
            "parents_guide_url": f"https://www.imdb.com/title/{imdb_id}/parentalguide/" if imdb_id else None,
            "parents_guide": raw.get("parents_guide") or {},
            "age": age_info["age"],
            "age_reasons": age_info["reasons"],
            "age_unknown": age_info["unknown"],
            "age_estimated": bool(age_info.get("estimated")) and age_source == "model",
            "age_source": age_source,
            "status": status,
            "error": raw.get("error") or (raw.get("guide_error") if not raw.get("parents_guide") else None),
            "watched": key in watched,
            "watched_on": watched.get(key),
        })
    return records


def year_label(raw, entry) -> str:
    start = raw.get("year") or entry.get("year")
    if not start:
        return ""
    if raw.get("kind") == "series":
        end = raw.get("year_end")
        if end and end != start:
            return f"{start}–{end}"
        return f"{start}–" if raw.get("ongoing") else str(start)
    return str(start)


def runtime_label(raw) -> str:
    mins = raw.get("runtime_min")
    if raw.get("kind") == "series":
        parts = []
        if mins:
            # OMDb gives per-episode length for most series but the whole run
            # for miniseries; nothing episodic is longer than 90 minutes.
            parts.append(f"≈{mins} min/ep" if mins <= 90 else f"{mins} min total")
        if raw.get("total_seasons"):
            n = raw["total_seasons"]
            parts.append(f"{n} season{'' if n == 1 else 's'}")
        return " · ".join(parts)
    return f"{mins} min" if mins else ""


def plain_list_html(entries, watched, version) -> str:
    """list.md as a bare page: one title per line, alphabetical, watched marked."""
    from html import escape
    items = []
    for e in entries:
        key = e["key"]
        text = key
        mark = ' <span class="w">watched</span>' if key in watched else ""
        items.append(f"<li>{escape(text)}{mark}</li>")
    n = len(entries)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cinema Indi list</title>
<link rel="stylesheet" href="style.css?v={version}">
<style>
  .plain {{ max-width: 40rem; margin: 0 auto; padding: 1.5rem; }}
  .plain h1 {{ margin: 0 0 0.25rem; font-size: 1.6rem; }}
  .plain .nav {{ display: flex; gap: 1rem; flex-wrap: wrap; color: var(--muted); margin: 0 0 1.25rem; font-size: 0.9rem; }}
  .plain ul {{ list-style: none; margin: 0; padding: 0; columns: 1; }}
  .plain li {{ padding: 0.2rem 0; border-bottom: 1px solid var(--line); }}
  .plain .w {{ color: var(--muted); font-size: 0.8rem; margin-left: 0.4rem; }}
  @media (min-width: 700px) {{ .plain ul {{ columns: 2; column-gap: 2rem; }} .plain li {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<main class="plain">
  <h1>Cinema Indi list</h1>
  <p class="nav"><a href="./">Full site</a> <a href="list.md">Raw list.md</a> <span>{n} film{"" if n == 1 else "s"}</span></p>
  <ul>
{chr(10).join("    " + i for i in items)}
  </ul>
</main>
</body>
</html>
"""


def _asset_version(out) -> str:
    """Short content hash over the static assets, stable across identical builds."""
    import hashlib
    h = hashlib.sha1()
    for name in ("app.js", "style.css"):
        h.update((out / name).read_bytes())
    return h.hexdigest()[:10]


def explain(records) -> str:
    lines = ["| Title | Year | Rated | " + " | ".join(k.capitalize() for k in CATEGORY_LABELS) + " | Age | Why |",
             "|---|---|---|" + "---|" * len(CATEGORY_LABELS) + "---|---|"]
    for r in sorted(records, key=lambda r: (r["age"] is None, r["age"] or 0, r["alpha_key"])):
        sev = " | ".join((r["parents_guide"].get(k) or "?") for k in CATEGORY_LABELS)
        age = (f"{r['age']}+" + {"label": " (label)", "override": " (override)"}.get(r.get("age_source"), "") + ("~" if r.get("age_estimated") else "")) if r["age"] is not None else "?"
        lines.append(f"| {r['title']} | {r['year'] or ''} | {r['rated'] or ''} | {sev} | {age} | {'; '.join(r['age_reasons'])} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--explain", action="store_true", help="print the age table")
    ap.add_argument("--out", default=str(SITE_OUT))
    args = ap.parse_args(argv)

    entries = parse_list(LIST_PATH.read_text(encoding="utf-8"))
    cache = load_json(FILMS_PATH, {})
    overrides = {k: v for k, v in load_json(OVERRIDES_PATH, {}).items() if not k.startswith("_")}
    rules = load_json(RULES_PATH, None)
    if rules is None:
        print(f"missing {RULES_PATH}", file=sys.stderr)
        return 1

    watched = parse_watched(WATCHED_PATH.read_text(encoding="utf-8")) if WATCHED_PATH.exists() else {}
    labels = {k: v for k, v in load_json(LABELS_PATH, {}).items() if not k.startswith("_")}
    known = {e["key"] for e in entries}
    for k in watched:
        if k not in known:
            print(f"WARNING watched.md: '{k}' is not a line in list.md")
    for k in labels:
        if k not in known:
            print(f"WARNING labels.json: '{k}' is not a line in list.md")
    records = build_records(entries, cache, overrides, rules, watched, labels)
    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE_SRC, out)
    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d"),
        "rules": rules,
        "categories": CATEGORY_LABELS,
        "icons": CATEGORY_ICONS,
        "films": records,
    }
    (out / "films.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    # Cache-bust the static assets: GitHub Pages serves them with a 10-minute
    # max-age, so without this a redeploy is invisible until the cache expires.
    version = _asset_version(out)
    html = (out / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="style.css"', f'href="style.css?v={version}"').replace('src="app.js"', f'src="app.js?v={version}"')
    (out / "index.html").write_text(html, encoding="utf-8")
    # A plain rendering of list.md for quick "is it on the list?" checks, plus
    # the raw file itself.
    (out / "list.html").write_text(plain_list_html(entries, watched, version), encoding="utf-8")
    (out / "list.md").write_text(LIST_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"built {len(records)} films into {out} ({sum(r['watched'] for r in records)} watched)")
    if args.explain:
        print(explain(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
