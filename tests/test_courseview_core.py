import json
import unittest
from unittest.mock import patch

from ai_caddie.courses import courseview_core as core


def _hole(number: int) -> dict:
    # Exact public CourseView field names and representative Cypress Point values.
    return {
        "HoleNumber": number,
        "InfoMask": 4,
        "GreenRadii": [15, 15, 10, 9, 8, 9, 10, 14, 18, 19] * 3,
        "Line": [{
            "LineId": 30_883_742 + number,
            "LineCode": 3240,
            "CoordinateCount": 2,
            "Length": 508,
            "Flags": 1_073_741_824,
            "Points": [
                {
                    "PointNumber": 2,
                    "Latitude": 436_388_613,
                    "Longitude": -1_455_113_802,
                    "Closure": 0,
                    "Flag": 0,
                },
                {
                    "PointNumber": 1,
                    "Latitude": 436_433_113,
                    "Longitude": -1_455_147_649,
                    "Closure": 0,
                    "Flag": 0,
                },
            ],
        }],
        "Pars": [{"Par": 5, "Type": 0, "Sequence": 1, "PlayerType": 1}],
        "Hazards": [{
            "Code": 18124,
            "Flags": 10,
            "Latitude": 436_392_717,
            "Longitude": -1_455_116_523,
        }],
        "Handicaps": [{
            "Handicap": 1,
            "TeeType": "NotSpecified",
            "PlayerType": 1,
        }],
    }


def _payload() -> dict:
    return {
        "BuildId": 309,
        "GlobalLayoutId": 3881,
        "Group": 0,
        "Holes": [_hole(2), _hole(1)],
        "Tees": [{
            "TeeType": "Championship",
            "PlayerType": 1,
            "Rating": 73.1,
            "Slope": 141,
            "IsGarminEstimated": False,
        }],
    }


class CourseViewCoreParserTests(unittest.TestCase):
    def test_normalizes_real_shape_sorts_holes_and_decodes_coordinates(self) -> None:
        parsed = core.parse_course_data_json(
            json.dumps(_payload()).encode(),
            expected_build_id=309,
            expected_global_layout_id=3881,
            includes_hazard_lines=True,
        )

        self.assertEqual(parsed["schema"], "garmin-course-data-core-v1")
        self.assertEqual(parsed["sourceVariant"], "medium-plus")
        self.assertEqual([hole["holeNumber"] for hole in parsed["holes"]], [1, 2])
        hole = parsed["holes"][1]
        self.assertEqual(len(hole["greenRadii"]), 30)
        self.assertEqual([p["pointNumber"] for p in hole["lines"][0]["points"]], [1, 2])
        self.assertEqual(hole["lines"][0]["role"], "route")
        self.assertEqual(hole["lines"][0]["pointOrder"], "tee-to-green")
        self.assertEqual(hole["hazardAnchors"][0]["code"], 18124)
        self.assertEqual(hole["hazardAnchors"][0]["surface"], "bunker")
        self.assertAlmostEqual(
            hole["lines"][0]["points"][0]["latitude"],
            36.581400940194726,
        )
        self.assertAlmostEqual(
            hole["lines"][0]["points"][0]["longitude"],
            -121.96906694211066,
        )
        self.assertEqual(parsed["tees"][0]["teeType"], "Championship")

    def test_only_cross_checked_hazard_codes_receive_surface_semantics(self) -> None:
        payload = _payload()
        payload["Holes"] = [payload["Holes"][0]]
        line = payload["Holes"][0]["Line"][0]
        line["LineCode"] = 3241
        payload["Holes"][0]["Hazards"][0]["Code"] = 18123
        parsed = core.parse_course_data_json(payload)
        self.assertEqual(parsed["holes"][0]["lines"][0]["surface"], "water")
        self.assertEqual(
            parsed["holes"][0]["lines"][0]["pointOrder"],
            "tee-side-to-green-side",
        )
        self.assertEqual(parsed["holes"][0]["hazardAnchors"][0]["surface"], "water")

        line["LineCode"] = 3244
        payload["Holes"][0]["Hazards"][0]["Code"] = 18125
        unknown = core.parse_course_data_json(payload)["holes"][0]
        self.assertEqual(unknown["lines"][0]["role"], "unknown")
        self.assertIsNone(unknown["lines"][0]["surface"])
        self.assertIsNone(unknown["hazardAnchors"][0]["surface"])

    def test_rejects_response_bound_to_another_build_or_layout(self) -> None:
        with self.assertRaisesRegex(ValueError, "BuildId"):
            core.parse_course_data_json(_payload(), expected_build_id=313)
        with self.assertRaisesRegex(ValueError, "GlobalLayoutId"):
            core.parse_course_data_json(_payload(), expected_global_layout_id=31669)

    def test_rejects_duplicate_holes_bad_radii_and_bad_coordinate_count(self) -> None:
        duplicate = _payload()
        duplicate["Holes"][1]["HoleNumber"] = 2
        with self.assertRaisesRegex(ValueError, "repeats HoleNumber"):
            core.parse_course_data_json(duplicate)

        bad_radii = _payload()
        bad_radii["Holes"][0]["GreenRadii"] = [10] * 29
        with self.assertRaisesRegex(ValueError, "30 non-negative"):
            core.parse_course_data_json(bad_radii)

        bad_count = _payload()
        bad_count["Holes"][0]["Line"][0]["CoordinateCount"] = 3
        with self.assertRaisesRegex(ValueError, "does not match Points"):
            core.parse_course_data_json(bad_count)


class CourseViewCoreFetchTests(unittest.TestCase):
    def test_fetches_medium_plus_json_and_binds_response(self) -> None:
        body = json.dumps(_payload()).encode()
        with patch.object(core, "_fetch_course_data_bytes", return_value=body) as fetch:
            parsed = core.fetch_course_data(
                309,
                3881,
                include_hazard_lines=True,
                base_url="https://omt.example/CourseViewData/",
            )

        fetch.assert_called_once_with(
            "https://omt.example/CourseViewData/courseData/309,3881,32/Hazards"
        )
        self.assertEqual(parsed["sourceVariant"], "medium-plus")

    def test_rejects_non_positive_identifiers_without_fetch(self) -> None:
        with patch.object(core, "_fetch_course_data_bytes") as fetch:
            with self.assertRaisesRegex(ValueError, "must be positive"):
                core.fetch_course_data(0, 3881)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
