"""Tee-picker list: the `course_tee_options` builder + the public GET /courses/{id}/tees endpoint.

The builder is the single source for the pre-round tee picker (colour + total yards + default). It is
injectable so these tests are hermetic (no real geometry/CourseView files). unittest on purpose — CI
runs `unittest discover`.
"""

from __future__ import annotations

import unittest
from unittest.mock import call, patch

from fastapi.testclient import TestClient

from ai_caddie.caddie.analysis import _normalize_tee_color, _selected_tee, course_tee_options
from server_v2.main import app


def _geometry_with_tees(set_to_distance: dict[int, float]) -> dict:
    """One hole's geometry with a tee per (geometry set → tee→target distance in metres)."""
    tees = [
        {"tee_index": index, "sets": [set_num], "position": [0.0, 0.0], "target_distance_m": distance}
        for index, (set_num, distance) in enumerate(set_to_distance.items())
    ]
    return {"hazards": {"tees": tees}}


class CourseTeeOptionsTests(unittest.TestCase):
    def test_release_tee_indices_drive_names_and_distances(self) -> None:
        # Garmin's geometry ``sets`` are release tee indices, not fixed colour slots.
        # Pebble Beach is Blue=1, Gold=2, White=3, Green=4, Red=5; treating set 1 as
        # universally Black makes a selected Blue tee start from the wrong physical tee.
        release_tees = [
            {"name": "Blue", "gender": "MEN", "index": 1, "slopeRating": 144, "courseRating": 74.9},
            {"name": "Gold", "gender": "MEN", "index": 2},
            {"name": "White", "gender": "MEN", "index": 3},
            {"name": "Green", "gender": "MEN", "index": 4},
            {"name": "Red", "gender": "MEN", "index": 5},
        ]
        per_hole = _geometry_with_tees({1: 300.0, 2: 280.0, 3: 260.0, 4: 240.0, 5: 220.0})

        result = course_tee_options(
            10283,
            tee_name_resolver=lambda gid: release_tees,
            holes_resolver=lambda gid: [1, 2],
            geometry_loader=lambda gid, hole: per_hole,
        )

        self.assertEqual(
            [(tee["teeBox"], tee["name"], tee["set"]) for tee in result["tees"]],
            [
                ("blue", "Blue", 1),
                ("gold", "Gold", 2),
                ("white", "White", 3),
                ("green", "Green", 4),
                ("red", "Red", 5),
            ],
        )
        self.assertEqual(result["tees"][0]["yards"], round(600.0 * 1.09361))
        self.assertEqual(result["tees"][0]["slopeRating"], 144)
        self.assertEqual(result["tees"][0]["courseRating"], 74.9)
        self.assertEqual(result["defaultTeeBox"], "blue")

    def test_selected_tee_resolves_colour_through_release_index(self) -> None:
        geometry = {
            "hazards": {
                "globalId": 10283,
                "tees": [
                    {"tee_index": 1, "sets": [1], "position": [0.0, 0.0], "target_distance_m": 300.0},
                    {"tee_index": 2, "sets": [2], "position": [1.0, 1.0], "target_distance_m": 280.0},
                ],
            }
        }
        release_tees = [
            {"name": "Blue", "gender": "MEN", "index": 1},
            {"name": "Gold", "gender": "MEN", "index": 2},
        ]

        with patch(
            "ai_caddie.courses.course_reference.courseview_tees",
            create=True,
            return_value=release_tees,
        ):
            selected = _selected_tee(geometry, "blue")

        self.assertIsNotNone(selected)
        self.assertEqual(selected["tee_index"], 1)

    def test_yardage_summed_per_set_across_holes(self) -> None:
        # 2 holes, each with black(set1)=300m, blue(set2)=280m, red(set5)=250m.
        per_hole = _geometry_with_tees({1: 300.0, 2: 280.0, 5: 250.0})
        result = course_tee_options(
            31795,
            tee_name_resolver=lambda gid: ["Black", "Blue", "Red"],
            holes_resolver=lambda gid: [1, 2],
            geometry_loader=lambda gid, hole: per_hole,
        )
        by_box = {tee["teeBox"]: tee for tee in result["tees"]}
        self.assertEqual(set(by_box), {"black", "blue", "red"})
        # Two holes × 300 m = 600 m → yards.
        self.assertEqual(by_box["black"]["yards"], round(600.0 * 1.09361))
        self.assertEqual(by_box["black"]["holeCount"], 2)
        self.assertEqual(by_box["black"]["name"], "Black")
        self.assertEqual(by_box["black"]["set"], 1)
        # Ordered longest → shortest (set number ascending).
        self.assertEqual([tee["teeBox"] for tee in result["tees"]], ["black", "blue", "red"])

    def test_shared_tee_box_deduped_red_not_equal_black(self) -> None:
        # A course with only 3 physical tees: tee idx3 serves sets [6,5,2,1] (black+blue+red share it).
        # Must show each distinct tee once — never red at black's distance (was 72/104 courses' bug).
        per_hole = {"hazards": {"tees": [
            {"tee_index": 1, "sets": [8, 4], "position": [0.0, 0.0], "target_distance_m": 313.0},
            {"tee_index": 2, "sets": [7, 3], "position": [0.0, 0.0], "target_distance_m": 333.7},
            {"tee_index": 3, "sets": [6, 5, 2, 1], "position": [0.0, 0.0], "target_distance_m": 350.6},
        ]}}
        result = course_tee_options(
            30249, tee_name_resolver=lambda gid: [],
            holes_resolver=lambda gid: [1], geometry_loader=lambda gid, hole: per_hole,
        )
        yards = [tee["yards"] for tee in result["tees"] if tee["yards"] is not None]
        self.assertEqual(len(yards), len(set(yards)), "no two tees may share a yardage (shared tee box)")
        self.assertEqual(len(result["tees"]), 3)  # 3 distinct physical tees, not 5 canonical colours

    def test_default_is_blue_when_present(self) -> None:
        result = course_tee_options(
            1,
            tee_name_resolver=lambda gid: ["Blue", "White"],
            holes_resolver=lambda gid: [1],
            geometry_loader=lambda gid, hole: _geometry_with_tees({2: 300.0, 3: 280.0}),
        )
        self.assertEqual(result["defaultTeeBox"], "blue")
        self.assertTrue(next(tee for tee in result["tees"] if tee["teeBox"] == "blue")["default"])
        self.assertEqual(sum(1 for tee in result["tees"] if tee["default"]), 1)

    def test_default_is_longest_when_no_blue(self) -> None:
        result = course_tee_options(
            1,
            tee_name_resolver=lambda gid: ["Black", "White", "Red"],
            holes_resolver=lambda gid: [1],
            geometry_loader=lambda gid, hole: _geometry_with_tees({1: 300.0, 3: 280.0, 5: 250.0}),
        )
        self.assertEqual(result["defaultTeeBox"], "black")

    def test_missing_yardage_is_null_not_faked(self) -> None:
        # CourseView names a Gold tee, but there is no geometry for it → yards null, still listed.
        result = course_tee_options(
            1,
            tee_name_resolver=lambda gid: ["Gold"],
            holes_resolver=lambda gid: [1],
            geometry_loader=lambda gid, hole: {"hazards": {"tees": []}},
        )
        by_box = {tee["teeBox"]: tee for tee in result["tees"]}
        self.assertIn("gold", by_box)
        self.assertIsNone(by_box["gold"]["yards"])

    def test_degrades_to_generic_tiers_when_nothing_known(self) -> None:
        result = course_tee_options(
            1,
            tee_name_resolver=lambda gid: [],
            holes_resolver=lambda gid: [1],
            geometry_loader=lambda gid, hole: {"hazards": {"tees": []}},
        )
        self.assertEqual([tee["name"] for tee in result["tees"]], ["长台", "中台", "短台"])
        self.assertTrue(all(tee["yards"] is None for tee in result["tees"]))
        self.assertEqual(result["defaultTeeBox"], "black")  # longest generic tier (no blue)

    def test_chinese_courseview_names_map_to_colours(self) -> None:
        result = course_tee_options(
            1,
            tee_name_resolver=lambda gid: ["蓝", "白"],
            holes_resolver=lambda gid: [1],
            geometry_loader=lambda gid, hole: _geometry_with_tees({2: 300.0, 3: 280.0}),
        )
        by_box = {tee["teeBox"]: tee for tee in result["tees"]}
        self.assertEqual(by_box["blue"]["name"], "蓝")
        self.assertEqual(by_box["white"]["name"], "白")

    def test_normalize_tee_color(self) -> None:
        self.assertEqual(_normalize_tee_color("Championship"), "black")
        self.assertEqual(_normalize_tee_color("Blue Tee"), "blue")
        self.assertEqual(_normalize_tee_color("金"), "gold")
        self.assertIsNone(_normalize_tee_color("Mystery"))
        self.assertIsNone(_normalize_tee_color(None))


class CourseTeesEndpointTests(unittest.TestCase):
    def test_endpoint_is_public_and_well_formed(self) -> None:
        client = TestClient(app)
        # No token → public course knowledge (like /topo.png). Never 401/403.
        resp = client.get("/api/v2/courses/31795/tees")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["schema"], "ai-caddie-course-tees-v1")
        self.assertEqual(body["globalId"], 31795)
        self.assertIn("defaultTeeBox", body)
        self.assertIsInstance(body["tees"], list)
        self.assertTrue(body["tees"])  # at minimum the generic fallback tiers
        for tee in body["tees"]:
            self.assertIn("teeBox", tee)
            self.assertIn("name", tee)
            self.assertIn("yards", tee)  # may be None — honest when geometry is absent
            self.assertIn("set", tee)
            self.assertIn("default", tee)
        self.assertEqual(sum(1 for tee in body["tees"] if tee["default"]), 1)
        self.assertIn(body["defaultTeeBox"], {tee["teeBox"] for tee in body["tees"]})

    @patch.dict(
        "os.environ",
        {"AI_CADDIE_ADMIN_TOKEN": "tee-test-token", "AI_CADDIE_SECURITY_PROFILE": "private"},
    )
    def test_ensure_release_requires_authentication(self) -> None:
        response = TestClient(app).get("/api/v2/courses/10283/tees?ensure_release=true")
        self.assertEqual(response.status_code, 401)

    @patch.dict(
        "os.environ",
        {"AI_CADDIE_ADMIN_TOKEN": "tee-test-token", "AI_CADDIE_SECURITY_PROFILE": "private"},
    )
    def test_ensure_release_fetches_cold_tee_metadata_without_preparing_geometry(self) -> None:
        release_tees = [
            {"name": "Blue", "gender": "MEN", "index": 1},
            {"name": "Gold", "gender": "MEN", "index": 2},
        ]
        expected_options = {
            "defaultTeeBox": "blue",
            "tees": [
                {
                    "teeBox": "blue",
                    "name": "Blue",
                    "set": 1,
                    "yards": 6828,
                    "holeCount": 18,
                    "default": True,
                }
            ],
        }
        with (
            patch(
                "ai_caddie.courses.course_reference.courseview_tees",
                side_effect=[[], release_tees],
            ) as fetch_release,
            patch("ai_caddie.caddie.mobile_live._ensure_geometry_for_course") as prepare_geometry,
            patch("ai_caddie.caddie.analysis.course_tee_options", return_value=expected_options) as options,
        ):
            response = TestClient(app).get(
                "/api/v2/courses/10283/tees?ensure_release=true",
                headers={"x-ai-caddie-admin-token": "tee-test-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            fetch_release.call_args_list,
            [call(10283, allow_fetch=False), call(10283, allow_fetch=True)],
        )
        prepare_geometry.assert_not_called()
        options.assert_called_once()
        self.assertEqual(response.json()["tees"], expected_options["tees"])

    @patch.dict(
        "os.environ",
        {"AI_CADDIE_ADMIN_TOKEN": "tee-test-token", "AI_CADDIE_SECURITY_PROFILE": "private"},
    )
    def test_ensure_release_returns_cached_tees_before_background_refresh(self) -> None:
        cached_tees = [{"name": "Blue", "gender": "MEN", "index": 1}]
        expected_options = {
            "defaultTeeBox": "blue",
            "tees": [
                {
                    "teeBox": "blue",
                    "name": "Blue",
                    "set": 1,
                    "yards": 6377,
                    "holeCount": 18,
                    "default": True,
                }
            ],
        }
        def release_lookup(global_id: int, *, allow_fetch: bool) -> list[dict]:
            self.assertEqual(global_id, 31793)
            return cached_tees

        with (
            patch(
                "ai_caddie.courses.course_reference.courseview_tees",
                side_effect=release_lookup,
            ) as fetch_release,
            patch("ai_caddie.caddie.analysis.course_tee_options", return_value=expected_options),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/v2/courses/31793/tees?ensure_release=true",
                    headers={"x-ai-caddie-admin-token": "tee-test-token"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["tees"], expected_options["tees"])

        self.assertEqual(
            fetch_release.call_args_list,
            [call(31793, allow_fetch=False), call(31793, allow_fetch=True)],
        )


if __name__ == "__main__":
    unittest.main()
