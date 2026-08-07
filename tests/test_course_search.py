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
        self.assertEqual(c["build_id"], 266)
        self.assertEqual(c["name"], "Nanjing Zhongshan International Golf Club ~ C Valley")
        self.assertEqual(c["holes"], 9)
        self.assertEqual(c["province"], "jiangsu")
        self.assertIn("Nanjing", c["city"])
        self.assertAlmostEqual(c["latitude"], 32.081172466278076)
        self.assertAlmostEqual(c["longitude"], 118.87230634689331)
        self.assertIs(c["supports_nine_plus_nine"], True)
        self.assertEqual(c["number_of_nine_hole_courses"], 3)
        self.assertIsNone(c["associated_dual_green_course_layout_id"])
        self.assertIs(c["has_green_contour"], True)
        self.assertEqual({31934, 31935, 31936} & set(by_gid), {31934, 31935, 31936})

    def test_coordinate_decoder_supports_western_longitudes_and_rejects_invalid_values(self) -> None:
        western_raw = (1 << 64) - 5_704_253
        self.assertAlmostEqual(
            cs._garmin_coordinate(western_raw, latitude=False),
            -122.39999055862427,
        )
        self.assertIsNone(cs._garmin_coordinate(5_000_000, latitude=True))

    def test_boundaries_coordinates_use_32_bit_semicircles(self) -> None:
        self.assertAlmostEqual(
            cs._garmin_coordinate(271_300_473, latitude=True, bits=31),
            22.74014295078814,
        )
        self.assertAlmostEqual(
            cs._garmin_coordinate(1_360_925_062, latitude=False, bits=31),
            114.07142093405128,
        )

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

    def test_location_search_uses_boundaries_endpoint_and_ranks_by_distance(self) -> None:
        rows = [
            {
                "global_id": 2, "name": "Mission Far", "holes": 18,
                "city": "Far", "province": None, "latitude": 23.5, "longitude": 114.5,
            },
            {
                "global_id": 1, "name": "Mission Near", "holes": 18,
                "city": "Shenzhen", "province": "Guangdong", "latitude": 22.7402, "longitude": 114.0715,
            },
        ]
        with (
            patch.object(cs, "_fetch_search", return_value=b"boundary") as fetch,
            patch.object(cs, "parse_course_search", return_value=rows) as parse,
        ):
            matches = cs.courseview_search(
                "Mission", latitude=22.7401328, longitude=114.0714097
            )

        fetch.assert_called_once_with(
            "Mission",
            latitude=22.7401328,
            longitude=114.0714097,
            page=1,
            page_size=50,
        )
        parse.assert_called_once_with(b"boundary", coordinate_bits=31)
        self.assertEqual([match.global_id for match in matches], [1, 2])
        self.assertEqual(matches[0].distance_km, 0.0)

    def test_boundaries_url_uses_signed_32_bit_semicircles(self) -> None:
        with patch.object(cs, "fetch_bytes", return_value=b"ok") as fetch:
            self.assertEqual(
                cs._fetch_search("Mission Hills", latitude=22.7401328, longitude=114.0714097),
                b"ok",
            )
        url = fetch.call_args.args[0]
        self.assertIn("/Boundaries/1360924928,271300352,32/Courses", url)
        self.assertIn("courseName=Mission%20Hills", url)

    def test_plain_name_url_uses_explicit_provider_pagination(self) -> None:
        with patch.object(cs, "fetch_bytes", return_value=b"ok") as fetch:
            self.assertEqual(cs._fetch_search("Zhongshan", page=3, page_size=50), b"ok")
        url = fetch.call_args.args[0]
        self.assertIn("/CourseViewData/Courses?courseName=Zhongshan", url)
        self.assertIn("bits=23", url)
        self.assertIn("pageSize=50", url)
        self.assertIn("page=3", url)

    def test_name_search_collects_every_provider_page_and_deduplicates(self) -> None:
        pages = {
            1: [
                {"global_id": 1, "name": "Mission A", "holes": 9},
                {"global_id": 2, "name": "Mission B", "holes": 9},
            ],
            2: [
                {"global_id": 2, "name": "Mission B", "holes": 9},
                {"global_id": 3, "name": "Mission C", "holes": 9},
            ],
            3: [],
        }

        def fetch_page(*_args, page: int, **_kwargs) -> bytes:
            return str(page).encode()

        with (
            patch.object(cs, "_NEARBY_PAGE_SIZE", 2),
            patch.object(cs, "_fetch_search", side_effect=fetch_page) as fetch,
            patch.object(cs, "parse_course_search", side_effect=lambda pb, **_: pages[int(pb)]),
        ):
            matches = cs.courseview_search("Mission")

        self.assertEqual({match.global_id for match in matches}, {1, 2, 3})
        self.assertEqual(fetch.call_count, 3)

    def test_name_search_does_not_disguise_provider_failure_as_no_results(self) -> None:
        with patch.object(cs, "_fetch_search", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                cs.courseview_search("Mission Hills")

    def test_nearby_paginates_provider_catalog_and_sorts_by_true_distance(self) -> None:
        pages = {
            1: [
                {
                    "global_id": 2, "name": "Far", "holes": 18,
                    "city": "Shenzhen", "province": "Guangdong",
                    "latitude": 22.9, "longitude": 114.3,
                },
                {
                    "global_id": 1, "name": "Near", "holes": 9,
                    "city": "Shenzhen", "province": "Guangdong",
                    "latitude": 22.7402, "longitude": 114.0715,
                },
            ],
            2: [],
        }

        def fetch_page(*_args, page: int, **_kwargs) -> bytes:
            return str(page).encode()

        with (
            patch.object(cs, "_fetch_nearby_page", side_effect=fetch_page) as fetch,
            patch.object(cs, "parse_course_search", side_effect=lambda pb, **_: pages[int(pb)]),
        ):
            matches = cs.courseview_nearby(
                latitude=22.7401328,
                longitude=114.0714097,
                radius_km=50,
                page_size=2,
            )

        self.assertEqual([match.global_id for match in matches], [1, 2])
        self.assertEqual(matches[0].distance_km, 0.0)
        self.assertEqual(matches[0].ratio, 0.0)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[0].kwargs["page"], 1)
        self.assertEqual(fetch.call_args_list[1].kwargs["page"], 2)

    def test_nearby_url_includes_radius_metres_and_page(self) -> None:
        with patch.object(cs, "fetch_bytes", return_value=b"ok") as fetch:
            self.assertEqual(
                cs._fetch_nearby_page(
                    latitude=22.7401328,
                    longitude=114.0714097,
                    radius_km=50,
                    page=2,
                    page_size=50,
                ),
                b"ok",
            )
        url = fetch.call_args.args[0]
        self.assertIn("/Boundaries/1360924928,271300352,50000,32/Courses", url)
        self.assertIn("pageSize=50", url)
        self.assertIn("page=2", url)

    def test_nearby_rejects_invalid_location_or_radius_without_fetch(self) -> None:
        with patch.object(cs, "_fetch_nearby_page") as fetch:
            self.assertEqual(cs.courseview_nearby(91, 114, 50), [])
            self.assertEqual(cs.courseview_nearby(22, 181, 50), [])
            self.assertEqual(cs.courseview_nearby(22, 114, 0), [])
        fetch.assert_not_called()

    def test_nearby_does_not_disguise_provider_failure_as_no_results(self) -> None:
        with patch.object(cs, "_fetch_nearby_page", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                cs.courseview_nearby(22.74, 114.07, 50)


class CourseSearchEndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from server_v2.main import app
        return TestClient(app)

    def test_search_endpoint_returns_matches(self) -> None:
        from ai_caddie.courses import course_search
        from server_v2 import main as server_main

        canned = [course_search.CourseMatch(
            31936,
            "Nanjing Zhongshan ~ C Valley",
            9,
            "Nanjing",
            "jiangsu",
            0.9,
            32.08074331283569,
            118.87230634689331,
            0.4,
        )]
        with patch.object(server_main.course_search, "courseview_search", return_value=canned):
            r = self._client().get("/api/v2/courses/search", params={"name": "zhongshan"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["schema"], "ai-caddie-course-search-v1")
        self.assertEqual(body["query"], "zhongshan")
        self.assertEqual(body["matches"][0]["globalId"], 31936)
        self.assertEqual(body["matches"][0]["holes"], 9)
        self.assertAlmostEqual(body["matches"][0]["latitude"], 32.08074331283569)
        self.assertAlmostEqual(body["matches"][0]["longitude"], 118.87230634689331)
        self.assertEqual(body["matches"][0]["distanceKm"], 0.4)

    def test_search_endpoint_requires_location_pair(self) -> None:
        response = self._client().get(
            "/api/v2/courses/search",
            params={"name": "Mission", "latitude": 22.74},
        )
        self.assertEqual(response.status_code, 422)

    def test_search_endpoint_empty_on_no_match(self) -> None:
        from server_v2 import main as server_main

        with patch.object(server_main.course_search, "courseview_search", return_value=[]):
            r = self._client().get("/api/v2/courses/search", params={"name": "nope"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["matches"], [])

    def test_search_endpoint_reports_provider_failure(self) -> None:
        from server_v2 import main as server_main

        with patch.object(server_main.course_search, "courseview_search", side_effect=OSError("offline")):
            response = self._client().get(
                "/api/v2/courses/search",
                params={"name": "Mission Hills"},
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Garmin course catalogue unavailable")

    def test_nearby_endpoint_returns_provider_wide_matches(self) -> None:
        from ai_caddie.courses import course_search
        from server_v2 import main as server_main

        canned = [course_search.CourseMatch(
            31669,
            "Shenzhen Mission Hills ~ Els",
            9,
            "Shenzhen",
            "Guangdong",
            0.0,
            22.7402,
            114.0715,
            0.0,
        )]
        with patch.object(server_main.course_search, "courseview_nearby", return_value=canned) as nearby:
            response = self._client().get(
                "/api/v2/courses/nearby",
                params={"latitude": 22.7401328, "longitude": 114.0714097, "radius_km": 50},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema"], "ai-caddie-course-nearby-v1")
        self.assertEqual(response.json()["radiusKm"], 50)
        self.assertEqual(response.json()["matches"][0]["globalId"], 31669)
        nearby.assert_called_once_with(latitude=22.7401328, longitude=114.0714097, radius_km=50)

    def test_nearby_endpoint_bounds_radius(self) -> None:
        response = self._client().get(
            "/api/v2/courses/nearby",
            params={"latitude": 22.74, "longitude": 114.07, "radius_km": 201},
        )
        self.assertEqual(response.status_code, 422)

    def test_nearby_endpoint_reports_provider_failure(self) -> None:
        from server_v2 import main as server_main

        with patch.object(server_main.course_search, "courseview_nearby", side_effect=OSError("offline")):
            response = self._client().get(
                "/api/v2/courses/nearby",
                params={"latitude": 22.74, "longitude": 114.07},
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Garmin course catalogue unavailable")


if __name__ == "__main__":
    unittest.main()
