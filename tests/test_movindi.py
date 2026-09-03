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

    def test_first_sentence(self):
        self.assertEqual(m.first_sentence("A boy meets a girl. They dance."), "A boy meets a girl.")
        self.assertEqual(m.first_sentence("Dr. Brown builds a time machine. Chaos ensues."), "Dr. Brown builds a time machine.")
        self.assertEqual(m.first_sentence("N/A"), "")


class AgeRules(unittest.TestCase):
    def setUp(self):
        self.rules = m.load_json(m.RULES_PATH, None)

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


if __name__ == "__main__":
    unittest.main()
