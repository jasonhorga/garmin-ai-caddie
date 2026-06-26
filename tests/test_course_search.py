import unittest
from pathlib import Path
from unittest.mock import patch

from ai_caddie.courses import course_search as cs

FIX = Path(__file__).parent / "fixtures"


class ParseCourseSearchTests(unittest.TestCase):
    def test_parses_records_from_fixture(self) -> None:
        records = cs.parse_course_search((FIX / "courseview_search_zhongshan.pb").read_bytes())
        by_gid = {r["global_id"]: r for r in records}
        self.assertIn(31936, by_gid)
        c = by_gid[31936]
        self.assertEqual(c["name"], "Nanjing Zhongshan International Golf Club ~ C Valley")
        self.assertEqual(c["holes"], 9)
        self.assertEqual(c["province"], "jiangsu")
        self.assertIn("Nanjing", c["city"])
        self.assertEqual({31934, 31935, 31936} & set(by_gid), {31934, 31935, 31936})

    def test_empty_bytes_yields_no_records(self) -> None:
        self.assertEqual(cs.parse_course_search(b""), [])


class CourseviewSearchTests(unittest.TestCase):
    def _fixture(self) -> bytes:
        return (FIX / "courseview_search_zhongshan.pb").read_bytes()

    def test_ranks_and_returns_matches(self) -> None:
        with patch.object(cs, "_fetch_search", return_value=self._fixture()):
            matches = cs.courseview_search("Zhongshan C Valley")
        self.assertTrue(matches)
        self.assertEqual(matches[0].global_id, 31936)
        self.assertTrue(all(isinstance(m, cs.CourseMatch) for m in matches))
        self.assertTrue(matches[0].ratio >= matches[-1].ratio)

    def test_hole_count_guard_filters(self) -> None:
        with patch.object(cs, "_fetch_search", return_value=self._fixture()):
            matches = cs.courseview_search("Zhongshan", expected_holes=18)
        self.assertEqual(matches, [])

    def test_city_guard_filters(self) -> None:
        with patch.object(cs, "_fetch_search", return_value=self._fixture()):
            hit = cs.courseview_search("Zhongshan", city="Nanjing")
            miss = cs.courseview_search("Zhongshan", city="Shanghai")
        self.assertTrue(hit)
        self.assertEqual(miss, [])

    def test_short_query_returns_empty_without_fetch(self) -> None:
        with patch.object(cs, "_fetch_search") as fetch:
            self.assertEqual(cs.courseview_search("z"), [])
        fetch.assert_not_called()


class CourseSearchEndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from server_v2.main import app
        return TestClient(app)

    def test_search_endpoint_returns_matches(self) -> None:
        from ai_caddie.courses import course_search
        canned = [course_search.CourseMatch(31936, "Nanjing Zhongshan ~ C Valley", 9, "Nanjing", "jiangsu", 0.9)]
        with patch("server_v2.main.course_search.courseview_search", return_value=canned):
            r = self._client().get("/api/v2/courses/search", params={"name": "zhongshan"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["schema"], "ai-caddie-course-search-v1")
        self.assertEqual(body["query"], "zhongshan")
        self.assertEqual(body["matches"][0]["globalId"], 31936)
        self.assertEqual(body["matches"][0]["holes"], 9)

    def test_search_endpoint_empty_on_no_match(self) -> None:
        with patch("server_v2.main.course_search.courseview_search", return_value=[]):
            r = self._client().get("/api/v2/courses/search", params={"name": "nope"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["matches"], [])


if __name__ == "__main__":
    unittest.main()
