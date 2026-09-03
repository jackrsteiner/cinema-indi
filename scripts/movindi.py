"""Shared helpers for the movindi pipeline: list parsing, sort keys, age rules.

Standard library only so the GitHub Action needs no installs.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIST_PATH = ROOT / "list.md"
WATCHED_PATH = ROOT / "watched.md"
DATA_DIR = ROOT / "data"
FILMS_PATH = DATA_DIR / "films.json"
OVERRIDES_PATH = DATA_DIR / "overrides.json"
RULES_PATH = DATA_DIR / "age-rules.json"
LABELS_PATH = DATA_DIR / "labels.json"

ARTICLES = ("the ", "a ", "an ")

# IMDb Parents Guide category ids -> short keys used everywhere in this repo.
CATEGORY_KEYS = {
    "NUDITY": "sex",
    "VIOLENCE": "violence",
    "PROFANITY": "profanity",
    "ALCOHOL": "drugs",
    "FRIGHTENING": "frightening",
}
CATEGORY_ICONS = {
    "sex": "💋",
    "violence": "🪓",
    "profanity": "🤬",
    "drugs": "🍺",
    "frightening": "😱",
}
CATEGORY_LABELS = {
    "sex": "Sex & Nudity",
    "violence": "Violence & Gore",
    "profanity": "Profanity",
    "drugs": "Alcohol, Drugs & Smoking",
    "frightening": "Frightening & Intense Scenes",
}
SEVERITIES = ("None", "Mild", "Moderate", "Severe")

_PAREN_RE = re.compile(r"^(?P<title>.+?)\s*\((?P<extra>[^()]*)\)\s*$")
KINDS = ("film", "series")


def parse_entry(line: str) -> tuple[str, int | None, str]:
    """Split 'Title (2005 series)' into (title, year, kind).

    The parenthetical is only interpreted when it contains nothing but an
    optional 4-digit year and/or the word 'series'; anything else stays part
    of the title.
    """
    title, year, kind = line.strip(), None, "film"
    m = _PAREN_RE.match(title)
    if m:
        tokens = m.group("extra").split()
        years = [t for t in tokens if re.fullmatch(r"\d{4}", t)]
        series = [t for t in tokens if t.lower() == "series"]
        if tokens and len(years) + len(series) == len(tokens) and len(years) <= 1 and len(series) <= 1:
            title = m.group("title").strip()
            year = int(years[0]) if years else None
            kind = "series" if series else "film"
    return title, year, kind


def parse_list(text: str) -> list[dict]:
    """Parse list.md: one title per non-empty line, optional trailing
    '(YEAR)', '(series)' or '(YEAR series)'.

    Leading markdown bullets ("- ", "* ") are tolerated so the file still reads
    fine as markdown, but plain lines are the canonical format.
    """
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        title, year, kind = parse_entry(line)
        entries.append({"key": entry_key(title, year, kind), "title": title, "year": year, "kind": kind})
    return entries


_WATCHED_RE = re.compile(r"^(?P<key>.+?)(?:\s+(?P<date>\d{4}-\d{2}-\d{2}))?\s*$")


def parse_watched(text: str) -> dict:
    """Parse watched.md: one list.md line per row, optional trailing YYYY-MM-DD.

    Returns {key: date_or_None}. Rows are normalised through entry_key so
    'True Grit (2010)' matches the list entry of the same name.
    """
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        m = _WATCHED_RE.match(line)
        title, year, kind = parse_entry(m.group("key"))
        out[entry_key(title, year, kind)] = m.group("date")
    return out


def entry_key(title: str, year: int | None, kind: str = "film") -> str:
    """Stable identifier for a list entry, used as the cache key in films.json."""
    extra = ([str(year)] if year else []) + (["series"] if kind == "series" else [])
    return f"{title} ({' '.join(extra)})" if extra else title


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def sort_title(title: str) -> str:
    """Title with a leading article removed: 'The Graduate' -> 'Graduate'."""
    t = title.strip()
    low = t.lower()
    for art in ARTICLES:
        if low.startswith(art):
            return t[len(art):].lstrip()
    return t


def alpha_key(title: str) -> str:
    return strip_accents(sort_title(title)).casefold()


def alpha_letter(title: str) -> str:
    k = alpha_key(title)
    return k[0].upper() if k and k[0].isalpha() else "#"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def check_list_sorted(entries: list[dict]) -> list[str]:
    """Return a list of problems if list.md is not alphabetical (ignoring articles)."""
    problems = []
    keys = [alpha_key(e["title"]) for e in entries]
    for i in range(1, len(keys)):
        if keys[i] < keys[i - 1]:
            problems.append(f"'{entries[i]['title']}' should come before '{entries[i-1]['title']}'")
    seen = set()
    for e in entries:
        if e["key"] in seen:
            problems.append(f"duplicate entry '{e['key']}'")
        seen.add(e["key"])
    return problems


def first_sentence(text: str | None) -> str:
    """Deterministically cut a plot to its first sentence."""
    if not text or text == "N/A":
        return ""
    text = text.strip()
    # Cut at the first sentence-ending punctuation that is followed by whitespace
    # and a capital/quote/digit, skipping common abbreviations.
    abbrev = re.compile(r"(?:\b(?:Dr|Mr|Mrs|Ms|St|Jr|Sr|Lt|Sgt|Capt|Col|Gen|Prof|vs|Mt|U\.S|U\.K|D\.C|a\.m|p\.m|etc|Inc|No)|\b[A-Z])\.$", re.I)
    for m in re.finditer(r"[.!?]+(?=\s+[\"'A-Z0-9])", text):
        head = text[: m.end()]
        if abbrev.search(head):
            continue
        return head.strip()
    return text


# ---------------------------------------------------------------------------
# Age appropriateness (deterministic, driven entirely by data/age-rules.json)
# ---------------------------------------------------------------------------

def compute_age(film: dict, rules: dict) -> dict:
    """Return {'age': int|None, 'reasons': [str], 'unknown': bool}.

    age = max(rating floor, per-category floor for each Parents Guide severity)
    plus optional stacking bumps. Every number comes from the rules file.
    """
    rating = (film.get("rated") or "").strip()
    rating_floor = rules["rating_floor"].get(rating)
    reasons = []
    candidates = []
    if rating_floor is not None:
        candidates.append(rating_floor)
        reasons.append(f"Rated {rating} → {rating_floor}+")

    guide = film.get("parents_guide") or {}
    known_categories = 0
    counts = {s: 0 for s in SEVERITIES}
    for cat, sev in guide.items():
        if sev not in SEVERITIES or cat not in rules["category_floor"]:
            continue
        known_categories += 1
        counts[sev] += 1
        floor = rules["category_floor"][cat][sev]
        candidates.append(floor)
        if sev != "None":
            reasons.append(f"{CATEGORY_LABELS[cat]}: {sev} → {floor}+")

    if not candidates:
        return {"age": None, "reasons": ["No rating or Parents Guide data yet"], "unknown": True}

    age = max(candidates)
    # Keep only the reasons that actually set the age, so the card explains itself.
    driving = [r for r in reasons if r.endswith(f"→ {age}+")]

    stacking = rules.get("stacking", {})
    bump = 0
    mod_plus = counts["Moderate"] + counts["Severe"]
    if stacking.get("moderate_or_worse_count") and mod_plus >= stacking["moderate_or_worse_count"]:
        bump += stacking.get("moderate_bump", 0)
        driving.append(f"{mod_plus} categories Moderate or worse → +{stacking.get('moderate_bump', 0)}")
    if stacking.get("severe_count") and counts["Severe"] >= stacking["severe_count"]:
        bump += stacking.get("severe_bump", 0)
        driving.append(f"{counts['Severe']} categories Severe → +{stacking.get('severe_bump', 0)}")
    age += bump

    partial = rating_floor is None and known_categories < len(CATEGORY_LABELS)
    return {"age": age, "reasons": driving or reasons, "unknown": False, "partial": partial}


# ---------------------------------------------------------------------------
# Linear model (rules["model"] == "linear"): fitted to hand-labelled ages.
# ---------------------------------------------------------------------------

SEVERITY_INDEX = {s: i for i, s in enumerate(SEVERITIES)}


def severity_scores(film: dict) -> dict:
    """Continuous 0..3 score per category.

    Uses the vote-weighted mean (None=0, Mild=1, Moderate=2, Severe=3) when the
    per-level vote counts are cached, otherwise the index of the median level.
    """
    guide = film.get("parents_guide") or {}
    votes = film.get("parents_guide_votes") or {}
    scores = {}
    for cat in CATEGORY_LABELS:
        v = votes.get(cat) or {}
        total = sum(n for n in v.values() if isinstance(n, int))
        if total > 0:
            scores[cat] = sum(SEVERITY_INDEX.get(level, 0) * n for level, n in v.items()) / total
        elif guide.get(cat) in SEVERITY_INDEX:
            scores[cat] = float(SEVERITY_INDEX[guide[cat]])
    return scores


def effective_rating(film: dict, rules: dict) -> str:
    """The rating the model reasons about: TV ratings map onto MPAA ones via
    rules["rating_aliases"] (TV-PG -> PG, TV-14 -> PG-13, ...)."""
    rated = (film.get("rated") or "").strip()
    return (rules.get("rating_aliases") or {}).get(rated, rated)


def linear_terms(film: dict, rules: dict) -> list[tuple[str, float]]:
    """(label, contribution) pairs for the linear model, intercept first."""
    terms = [("base", float(rules.get("intercept", 0)))]
    scores = severity_scores(film)
    missing = float(rules.get("missing_severity", 0))
    for cat, w in (rules.get("category_weights") or {}).items():
        if not w:
            continue
        if cat in scores:
            terms.append((CATEGORY_LABELS.get(cat, cat), w * scores[cat]))
        elif missing:
            terms.append((f"{CATEGORY_LABELS.get(cat, cat)} (assumed)", w * missing))
    rated = effective_rating(film, rules)
    off = (rules.get("rating_offsets") or {}).get(rated)
    if off:
        shown = (film.get("rated") or "").strip()
        terms.append((f"Rated {shown}" + (f" (as {rated})" if shown != rated else ""), float(off)))
    for g in film.get("genre") or []:
        off = (rules.get("genre_offsets") or {}).get(g)
        if off:
            terms.append((g, float(off)))
    kind_off = (rules.get("kind_offsets") or {}).get(film.get("kind") or "film")
    if kind_off:
        terms.append(((film.get("kind") or "film").capitalize(), float(kind_off)))
    for field, spec in (rules.get("numeric") or {}).items():
        val = film.get(field)
        if spec.get("films_only") and film.get("kind") == "series":
            continue
        if isinstance(val, (int, float)) and spec.get("weight"):
            terms.append((spec.get("label", field), spec["weight"] * (val - spec.get("center", 0))))
    return terms


def compute_age_linear(film: dict, rules: dict) -> dict:
    if not film.get("imdb_id"):
        return {"age": None, "reasons": ["Not looked up yet"], "unknown": True, "estimated": False}
    scores = severity_scores(film)
    terms = linear_terms(film, rules)
    raw = sum(v for _, v in terms)
    age = int(raw + 0.5)  # round half up
    lo, hi = rules.get("min_age", 0), rules.get("max_age", 18)
    age = max(lo, min(hi, age))
    shown = [terms[0]] + sorted(terms[1:], key=lambda t: -abs(t[1]))
    reasons = [f"{label} {val:+.1f}" if label != "base" else f"base {val:.1f}" for label, val in shown if abs(val) >= 0.05]
    reasons.append(f"= {raw:.1f} → {age}+")
    # Optional hard floors by rating for parts of the scale no label calibrates.
    rated = effective_rating(film, rules)
    floor = (rules.get("rating_floor") or {}).get(rated)
    if floor is not None and floor > age:
        age = floor
        reasons.append(f"floor for {rated} → {floor}+")
    # An estimate when IMDb has no Parents Guide for the film: the severity
    # terms fall back to missing_severity (default None) and the card says so.
    missing_cats = [CATEGORY_LABELS[c] for c in CATEGORY_LABELS if c not in scores]
    estimated = bool(missing_cats)
    if estimated:
        what = "all categories" if len(missing_cats) == len(CATEGORY_LABELS) else ", ".join(missing_cats)
        level = SEVERITIES[int(round(float(rules.get("missing_severity", 0))))] if 0 <= float(rules.get("missing_severity", 0)) <= 3 else "?"
        reasons.append(f"Estimate: no Parents Guide on IMDb for {what} (assumed {level})")
    return {"age": age, "reasons": reasons, "unknown": False, "estimated": estimated}


_compute_age_floors = compute_age


def compute_age(film: dict, rules: dict) -> dict:  # noqa: F811
    if rules.get("model") == "linear":
        return compute_age_linear(film, rules)
    return _compute_age_floors(film, rules)
