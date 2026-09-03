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
DATA_DIR = ROOT / "data"
FILMS_PATH = DATA_DIR / "films.json"
OVERRIDES_PATH = DATA_DIR / "overrides.json"
RULES_PATH = DATA_DIR / "age-rules.json"

ARTICLES = ("the ", "a ", "an ")

# IMDb Parents Guide category ids -> short keys used everywhere in this repo.
CATEGORY_KEYS = {
    "NUDITY": "sex",
    "VIOLENCE": "violence",
    "PROFANITY": "profanity",
    "ALCOHOL": "drugs",
    "FRIGHTENING": "frightening",
}
CATEGORY_LABELS = {
    "sex": "Sex & Nudity",
    "violence": "Violence & Gore",
    "profanity": "Profanity",
    "drugs": "Alcohol, Drugs & Smoking",
    "frightening": "Frightening & Intense Scenes",
}
SEVERITIES = ("None", "Mild", "Moderate", "Severe")

_ENTRY_RE = re.compile(r"^(?P<title>.+?)\s*(?:\((?P<year>\d{4})\))?\s*$")


def parse_list(text: str) -> list[dict]:
    """Parse list.md: one film per non-empty line, optional trailing (YEAR).

    Leading markdown bullets ("- ", "* ") are tolerated so the file still reads
    fine as markdown, but plain lines are the canonical format.
    """
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        m = _ENTRY_RE.match(line)
        title = m.group("title").strip()
        year = int(m.group("year")) if m.group("year") else None
        entries.append({"key": entry_key(title, year), "title": title, "year": year})
    return entries


def entry_key(title: str, year: int | None) -> str:
    """Stable identifier for a list entry, used as the cache key in films.json."""
    return f"{title} ({year})" if year else title


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
