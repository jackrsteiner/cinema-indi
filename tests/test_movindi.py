import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import movindi as m  # noqa: E402


class ListParsing(unittest.TestCase):
    def test_plain_and_year(self):
        entries = m.parse_list("Amélie\n\n- The Terminator\nTrue Grit (2010)\n# comment\n")
        self.assertEqual([e["key"] for e in entries], ["Amélie", "The Terminator", "True Grit (2010)"])
        self.assertEqual(entries[2]["year"], 2010)
        self.assertIsNone(entries[0]["year"])

    def test_series_marker(self):
        entries = m.parse_list("Bluey (series)\nFargo (2014 series)\nFargo (1996)\nScott Pilgrim vs. the World\n")
        self.assertEqual([e["kind"] for e in entries], ["series", "series", "film", "film"])
        self.assertEqual(entries[0]["key"], "Bluey (series)")
        self.assertEqual(entries[1], {"key": "Fargo (2014 series)", "title": "Fargo", "year": 2014, "kind": "series"})
        # Unknown parentheticals stay part of the title.
        self.assertEqual(m.parse_entry("Some Film (director's cut)"), ("Some Film (director's cut)", None, "film"))
        # watched.md rows normalise the same way, whatever the token order.
        self.assertEqual(m.parse_watched("Fargo (series 2014) 2026-01-02\n"), {"Fargo (2014 series)": "2026-01-02"})

    def test_sort_keys_ignore_articles_and_accents(self):
        self.assertEqual(m.sort_title("The Graduate"), "Graduate")
        self.assertEqual(m.sort_title("A Simple Favor"), "Simple Favor")
        self.assertEqual(m.sort_title("An American Tail"), "American Tail")
        self.assertEqual(m.sort_title("Theodore Rex"), "Theodore Rex")
        self.assertEqual(m.alpha_letter("Amélie"), "A")
        self.assertEqual(m.alpha_letter("2001: A Space Odyssey"), "#")
        self.assertEqual(m.alpha_letter("The Big Short"), "B")

    def test_repo_list_is_sorted(self):
        entries = m.parse_list(m.LIST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(m.check_list_sorted(entries), [])

    def test_unsorted_detected(self):
        entries = m.parse_list("Zorro\nAlien\nAlien\n")
        problems = m.check_list_sorted(entries)
        self.assertEqual(len(problems), 2)

    def test_parse_watched(self):
        w = m.parse_watched("# comment\nThe Princess Bride 2026-09-01\n- True Grit (2010)\nUp (2009) 2026-08-30\n")
        self.assertEqual(w, {"The Princess Bride": "2026-09-01", "True Grit (2010)": None, "Up (2009)": "2026-08-30"})

    def test_repo_watched_entries_exist_in_list(self):
        entries = {e["key"] for e in m.parse_list(m.LIST_PATH.read_text(encoding="utf-8"))}
        watched = m.parse_watched(m.WATCHED_PATH.read_text(encoding="utf-8")) if m.WATCHED_PATH.exists() else {}
        self.assertEqual([k for k in watched if k not in entries], [])

    def test_first_sentence(self):
        self.assertEqual(m.first_sentence("A boy meets a girl. They dance."), "A boy meets a girl.")
        self.assertEqual(m.first_sentence("Dr. Brown builds a time machine. Chaos ensues."), "Dr. Brown builds a time machine.")
        self.assertEqual(m.first_sentence("N/A"), "")


FLOOR_RULES = {
    "rating_floor": {"G": 5, "PG": 8, "PG-13": 12, "R": 15},
    "category_floor": {
        "violence": {"None": 0, "Mild": 7, "Moderate": 11, "Severe": 15},
        "frightening": {"None": 0, "Mild": 7, "Moderate": 10, "Severe": 14},
        "sex": {"None": 0, "Mild": 7, "Moderate": 13, "Severe": 17},
        "profanity": {"None": 0, "Mild": 7, "Moderate": 11, "Severe": 14},
        "drugs": {"None": 0, "Mild": 7, "Moderate": 11, "Severe": 14},
    },
    "stacking": {"moderate_or_worse_count": 3, "moderate_bump": 1, "severe_count": 2, "severe_bump": 1},
}


class AgeRules(unittest.TestCase):
    """The floors model (rules without "model": "linear")."""

    def setUp(self):
        self.rules = FLOOR_RULES

    def test_rating_alone(self):
        r = m.compute_age({"rated": "PG"}, self.rules)
        self.assertEqual(r["age"], self.rules["rating_floor"]["PG"])
        self.assertFalse(r["unknown"])

    def test_guide_raises_above_rating(self):
        film = {"rated": "PG", "parents_guide": {"violence": "Moderate", "profanity": "Mild",
                                                 "sex": "None", "drugs": "None", "frightening": "Mild"}}
        r = m.compute_age(film, self.rules)
        expected = self.rules["category_floor"]["violence"]["Moderate"]
        self.assertGreater(expected, self.rules["rating_floor"]["PG"])
        self.assertEqual(r["age"], expected)
        self.assertEqual(r["reasons"], [f"Violence & Gore: Moderate → {expected}+"])

    def test_stacking(self):
        film = {"rated": "R", "parents_guide": {"violence": "Severe", "profanity": "Severe",
                                                "sex": "Moderate", "drugs": "Moderate", "frightening": "Moderate"}}
        r = m.compute_age(film, self.rules)
        base = max(self.rules["rating_floor"]["R"], self.rules["category_floor"]["violence"]["Severe"],
                   self.rules["category_floor"]["profanity"]["Severe"], self.rules["category_floor"]["sex"]["Moderate"])
        # + 1 (>=3 moderate-or-worse) + 1 (>=2 severe)
        self.assertEqual(r["age"], base + 2)

    def test_unknown(self):
        r = m.compute_age({"rated": None, "parents_guide": {}}, self.rules)
        self.assertIsNone(r["age"])
        self.assertTrue(r["unknown"])

    def test_unlisted_rating_defers_to_guide(self):
        r = m.compute_age({"rated": "Approved", "parents_guide": {"violence": "Mild"}}, self.rules)
        self.assertEqual(r["age"], self.rules["category_floor"]["violence"]["Mild"])


class LinearModel(unittest.TestCase):
    def setUp(self):
        self.rules = m.load_json(m.RULES_PATH, None)
        self.assertEqual(self.rules.get("model"), "linear")

    def test_severity_scores_prefer_votes(self):
        film = {"parents_guide": {"violence": "Mild"}, "parents_guide_votes": {"violence": {"None": 3, "Mild": 1}}}
        self.assertAlmostEqual(m.severity_scores(film)["violence"], 0.25)
        film = {"parents_guide": {"violence": "Moderate"}}
        self.assertEqual(m.severity_scores(film)["violence"], 2.0)

    def test_terms_and_rounding(self):
        rules = {"model": "linear", "intercept": 3.4, "min_age": 3, "max_age": 18,
                 "category_weights": {"violence": 1.0}, "rating_offsets": {"PG": 0.5},
                 "genre_offsets": {"Animation": -0.6}, "numeric": {"runtime_min": {"weight": 0.01, "center": 100}}}
        guide = {c: "None" for c in m.CATEGORY_LABELS}; guide["violence"] = "Mild"
        film = {"imdb_id": "tt1", "rated": "PG", "genre": ["Animation"], "runtime_min": 110, "parents_guide": guide}
        r = m.compute_age(film, rules)
        # 3.4 + 1.0 + 0.5 - 0.6 + 0.1 = 4.4 -> 4
        self.assertEqual(r["age"], 4)
        self.assertEqual(r["reasons"][-1], "= 4.4 → 4+")

    def test_tv_ratings_alias_to_mpaa(self):
        rules = {"model": "linear", "intercept": 3, "category_weights": {}, "rating_offsets": {"PG": 1.0},
                 "rating_aliases": {"TV-PG": "PG"}, "rating_floor": {}}
        r = m.compute_age({"imdb_id": "tt1", "rated": "TV-PG", "parents_guide": {}}, rules)
        self.assertEqual(r["age"], 4)
        self.assertTrue(any("Rated TV-PG (as PG)" in x for x in r["reasons"]))
        self.assertEqual(m.effective_rating({"rated": "TV-14"}, self.rules), "PG-13")

    def test_runtime_term_skipped_for_series(self):
        rules = {"model": "linear", "intercept": 3, "category_weights": {},
                 "numeric": {"runtime_min": {"weight": -0.1, "center": 100, "films_only": True}}}
        film = {"imdb_id": "tt1", "runtime_min": 20, "parents_guide": {}}
        self.assertEqual(m.compute_age(dict(film, kind="film"), rules)["age"], 11)
        self.assertEqual(m.compute_age(dict(film, kind="series"), rules)["age"], 3)

    def test_rating_floor_applies(self):
        rules = {"model": "linear", "intercept": 3, "category_weights": {}, "rating_floor": {"R": 12}}
        r = m.compute_age({"imdb_id": "tt1", "rated": "R", "parents_guide": {"violence": "None"}}, rules)
        self.assertEqual(r["age"], 12)
        self.assertIn("floor for R → 12+", r["reasons"])

    def test_unknown_only_when_not_looked_up(self):
        r = m.compute_age({"rated": None, "parents_guide": {}}, self.rules)
        self.assertTrue(r["unknown"])

    def test_no_guide_gives_flagged_estimate(self):
        film = {"imdb_id": "tt0093488", "rated": None, "parents_guide": {}, "genre": ["Animation", "Short"],
                "runtime_min": 30, "imdb_rating": 8.6}
        r = m.compute_age(film, self.rules)
        self.assertFalse(r["unknown"])
        self.assertTrue(r["estimated"])
        self.assertIsInstance(r["age"], int)
        self.assertTrue(any(x.startswith("Estimate:") for x in r["reasons"]))
        full = dict(film, parents_guide={c: "None" for c in m.CATEGORY_LABELS})
        self.assertFalse(m.compute_age(full, self.rules)["estimated"])

    def test_missing_severity_setting(self):
        rules = {"model": "linear", "intercept": 3, "category_weights": {"violence": 1.0}, "missing_severity": 2}
        r = m.compute_age({"imdb_id": "tt1", "parents_guide": {}}, rules)
        self.assertEqual(r["age"], 5)

    def test_repo_rules_reproduce_labels(self):
        """The committed coefficients must keep reproducing the hand labels."""
        films = m.load_json(m.FILMS_PATH, {})
        labels = {"My Neighbor Totoro": 3, "Ponyo": 3, "Up (2009)": 4, "WALL-E": 4, "The Princess Bride": 5,
                  "Star Wars (1977)": 5, "The Empire Strikes Back": 6, "Indiana Jones and the Temple of Doom": 7}
        for k, t in labels.items():
            if k in films:
                self.assertEqual(m.compute_age(films[k], self.rules)["age"], t, k)


if __name__ == "__main__":
    unittest.main()
