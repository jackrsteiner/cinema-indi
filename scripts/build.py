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
    CATEGORY_LABELS, FILMS_PATH, LIST_PATH, OVERRIDES_PATH, ROOT, RULES_PATH,
    alpha_key, alpha_letter, compute_age, first_sentence, load_json, parse_list,
    sort_title,
)

SITE_SRC = ROOT / "site"
SITE_OUT = ROOT / "_site"


def build_records(entries, cache, overrides, rules) -> list[dict]:
    records = []
    for entry in entries:
        key = entry["key"]
        raw = dict(cache.get(key, {}))
        ov = overrides.get(key, {})
        # Overrides win over fetched values for the fields they name.
        for field in ("imdb_id", "title", "year", "rated", "series", "series_order"):
            if field in ov:
                raw[field] = ov[field]
        if "synopsis" in ov:
            raw["plot"] = ov["synopsis"]

        title = raw.get("title") or entry["title"]
        age_info = compute_age(raw, rules)
        if "age" in ov:
            age_info = {"age": ov["age"], "reasons": ["Set manually in overrides.json"], "unknown": False}
        poster = ov.get("poster") or raw.get("tmdb_poster") or raw.get("omdb_poster")
        imdb_id = raw.get("imdb_id")
        status = "error" if raw.get("error") else ("ok" if imdb_id else "pending")
        records.append({
            "key": key,
            "title": title,
            "sort_title": sort_title(title),
            "alpha_key": alpha_key(title),
            "letter": alpha_letter(title),
            "year": raw.get("year") or entry.get("year"),
            "rated": raw.get("rated") or raw.get("imdb_certificate"),
            "synopsis": first_sentence(raw.get("plot")),
            "poster": poster,
            "imdb_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None,
            "parents_guide_url": f"https://www.imdb.com/title/{imdb_id}/parentalguide/" if imdb_id else None,
            "series": raw.get("series"),
            "series_order": raw.get("series_order"),
            "parents_guide": raw.get("parents_guide") or {},
            "age": age_info["age"],
            "age_reasons": age_info["reasons"],
            "age_unknown": age_info["unknown"],
            "status": status,
            "error": raw.get("error") or (raw.get("guide_error") if not raw.get("parents_guide") else None),
        })
    return records


def explain(records) -> str:
    lines = ["| Title | Year | Rated | " + " | ".join(k.capitalize() for k in CATEGORY_LABELS) + " | Age | Why |",
             "|---|---|---|" + "---|" * len(CATEGORY_LABELS) + "---|---|"]
    for r in sorted(records, key=lambda r: (r["age"] is None, r["age"] or 0, r["alpha_key"])):
        sev = " | ".join((r["parents_guide"].get(k) or "?") for k in CATEGORY_LABELS)
        age = f"{r['age']}+" if r["age"] is not None else "?"
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

    records = build_records(entries, cache, overrides, rules)
    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE_SRC, out)
    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d"),
        "rules": rules,
        "categories": CATEGORY_LABELS,
        "films": records,
    }
    (out / "films.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"built {len(records)} films into {out}")
    if args.explain:
        print(explain(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
