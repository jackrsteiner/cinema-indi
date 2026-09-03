import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import enrich  # noqa: E402
from movindi import parse_list  # noqa: E402

OMDB_HIT = {"Title": "The Princess Bride", "Year": "1987", "Rated": "PG", "Plot": "A bedridden boy's grandfather reads him the story of a farmboy-turned-pirate. He encounters numerous obstacles.", "Poster": "https://m.media-amazon.com/x.jpg", "imdbID": "tt0093779", "Response": "True"}
OMDB_MISS = {"Response": "False", "Error": "Movie not found!"}
OMDB_SEARCH = {"Search": [{"Title": "WarGames", "Year": "1983", "imdbID": "tt0086567", "Type": "movie"}], "Response": "True"}
OMDB_WARGAMES = {"Title": "WarGames", "Year": "1983", "Rated": "PG", "Plot": "A young computer whiz kid accidentally connects into a top secret super-computer.", "Poster": "N/A", "imdbID": "tt0086567", "Response": "True"}
INTROSPECT = {"data": {"severity": {"fields": [{"name": "id"}, {"name": "text"}, {"name": "voteCount"}]}}}
GRAPHQL = {"data": {"title": {"id": "tt0093779", "certificate": {"rating": "PG"}, "parentsGuide": {"categories": [
    {"category": {"id": "NUDITY", "text": "Sex & Nudity"}, "severity": {"id": "MILD", "text": "Mild"},
     "totalSeverityVotes": 10, "severityBreakdown": [{"id": "NONE", "text": "None", "voteCount": 4},
                                                    {"id": "MILD", "text": "Mild", "voteCount": 6}]},
    {"category": {"id": "VIOLENCE", "text": "Violence & Gore"}, "severity": {"id": "MILD", "text": "Mild"}},
    {"category": {"id": "PROFANITY", "text": "Profanity"}, "severity": {"id": "MILD", "text": "Mild"}},
    {"category": {"id": "ALCOHOL", "text": "Alcohol, Drugs & Smoking"}, "severity": {"id": "MILD", "text": "Mild"}},
    {"category": {"id": "FRIGHTENING", "text": "Frightening & Intense Scenes"}, "severity": {"id": "MODERATE", "text": "Moderate"}},
]}}}}
TMDB = {"movie_results": [{"poster_path": "/abc.jpg"}]}


def fake_fetch(log):
    def fetch(url, data=None, headers=None):
        log.append(url)
        if url.startswith(enrich.IMDB_GRAPHQL_URL):
            assert headers and headers.get("x-imdb-client-name") == "imdb-web-next"
            if "__type" in data["query"]:
                return INTROSPECT
            assert "severityBreakdown { id text voteCount }" in data["query"], data["query"]
            return GRAPHQL
        if url.startswith(enrich.OMDB_URL):
            if "t=The+Princess+Bride" in url:
                return OMDB_HIT
            if "t=War+Games" in url:
                return OMDB_MISS
            if "s=War+Games" in url:
                return OMDB_SEARCH
            if "i=tt0086567" in url:
                return OMDB_WARGAMES
            if "i=tt0093779" in url:
                return OMDB_HIT
            return OMDB_MISS
        if "themoviedb.org" in url:
            return TMDB
        raise AssertionError("unexpected url " + url)
    return fetch


class Enrich(unittest.TestCase):
    def setUp(self):
        enrich._VOTE_FIELDS = None

    def test_full_pipeline_with_fallback_search(self):
        log = []
        entries = parse_list("The Princess Bride\nWar Games\nNo Such Film (1901)\n")
        out = enrich.enrich(entries, {}, {}, omdb_key="k", tmdb_key="t", fetch=fake_fetch(log), log=lambda *a: None)
        pb = out["The Princess Bride"]
        self.assertEqual(pb["imdb_id"], "tt0093779")
        self.assertEqual(pb["year"], 1987)
        self.assertEqual(pb["parents_guide"]["frightening"], "Moderate")
        self.assertEqual(pb["parents_guide_votes"]["sex"], {"None": 4, "Mild": 6})
        self.assertEqual(pb["genre"], [])
        self.assertNotIn("guide_votes_note", pb)
        self.assertEqual(pb["tmdb_poster"], "https://image.tmdb.org/t/p/w342/abc.jpg")
        self.assertNotIn("error", pb)
        wg = out["War Games"]
        self.assertEqual(wg["imdb_id"], "tt0086567")
        self.assertIsNone(wg["omdb_poster"])
        self.assertIn("error", out["No Such Film (1901)"])
        self.assertTrue(any("y=1901" in u for u in log))

    def test_cache_is_reused(self):
        log = []
        cached = {"The Princess Bride": {"imdb_id": "tt0093779", "title": "The Princess Bride", "genre": [],
                                         "parents_guide": {"violence": "Mild"}, "parents_guide_votes": {},
                                         "guide_fetched_at": enrich._now()}}
        entries = parse_list("The Princess Bride\n")
        out = enrich.enrich(entries, cached, {}, omdb_key="k", fetch=fake_fetch(log), log=lambda *a: None)
        self.assertEqual(log, [])
        self.assertEqual(out["The Princess Bride"]["imdb_id"], "tt0093779")

    def test_override_imdb_id_and_stale_guide_refresh(self):
        log = []
        cached = {"The Princess Bride": {"imdb_id": "tt0093779", "genre": [], "guide_fetched_at": "2000-01-01T00:00:00Z"}}
        entries = parse_list("The Princess Bride\n")
        out = enrich.enrich(entries, cached, {"The Princess Bride": {"imdb_id": "tt0093779"}},
                            omdb_key="k", fetch=fake_fetch(log), log=lambda *a: None)
        self.assertEqual([u for u in log if enrich.OMDB_URL in u], [])
        # one introspection call plus one guide query
        self.assertEqual(len([u for u in log if enrich.IMDB_GRAPHQL_URL in u]), 2)
        self.assertEqual(out["The Princess Bride"]["imdb_certificate"], "PG")

    def test_votes_query_falls_back(self):
        calls = []
        def fetch(url, data=None, headers=None):
            calls.append(data["query"] if data else url)
            if url.startswith(enrich.OMDB_URL):
                return OMDB_HIT
            if "__type" in data["query"]:
                return INTROSPECT
            if "severityBreakdown" in data["query"]:
                raise enrich.ApiError("HTTP 400: Cannot query field voteCount on type SeverityLevel", status=400)
            return GRAPHQL
        out = enrich.enrich(parse_list("The Princess Bride\n"), {}, {}, omdb_key="k", fetch=fetch, log=lambda *a: None)
        pb = out["The Princess Bride"]
        self.assertEqual(pb["parents_guide"]["frightening"], "Moderate")
        self.assertIn("guide_votes_note", pb)
        self.assertEqual(sum("severityBreakdown" in c for c in calls if isinstance(c, str)), 1)

    def test_introspection_without_vote_field_skips_votes(self):
        calls = []
        def fetch(url, data=None, headers=None):
            calls.append(data["query"] if data else url)
            if url.startswith(enrich.OMDB_URL):
                return OMDB_HIT
            if "__type" in data["query"]:
                return {"data": {"severity": {"fields": [{"name": "id"}, {"name": "text"}]}}}
            assert "severityBreakdown" not in data["query"]
            return GRAPHQL
        out = enrich.enrich(parse_list("The Princess Bride\n"), {}, {}, omdb_key="k", fetch=fetch, log=lambda *a: None)
        self.assertEqual(out["The Princess Bride"]["parents_guide_votes"], {})
        self.assertIn("guide_votes_note", out["The Princess Bride"])

    def test_missing_key_records_error(self):
        out = enrich.enrich(parse_list("X\n"), {}, {}, omdb_key="", fetch=fake_fetch([]), log=lambda *a: None)
        self.assertIn("OMDB_API_KEY", out["X"]["error"])

    def test_rejected_key_fails_fast(self):
        calls = []
        def fetch(url, data=None, headers=None):
            calls.append(url)
            raise enrich.ApiError("HTTP 401 from omdb: Invalid API key!", status=401)
        out = enrich.enrich(parse_list("A\nB\nC\n"), {}, {}, omdb_key="bad", fetch=fetch, log=lambda *a: None)
        self.assertEqual(len(calls), 1)
        for k in "ABC":
            self.assertIn("rejected the API key", out[k]["error"])

    def test_dropped_titles_leave_cache(self):
        out = enrich.enrich(parse_list("The Princess Bride\n"), {"Gone": {"imdb_id": "tt1"}, "The Princess Bride": {"imdb_id": "tt0093779", "genre": [], "parents_guide_votes": {}, "guide_fetched_at": enrich._now()}},
                            {}, omdb_key="k", fetch=fake_fetch([]), log=lambda *a: None)
        self.assertNotIn("Gone", out)


if __name__ == "__main__":
    unittest.main()
