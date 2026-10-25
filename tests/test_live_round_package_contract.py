"""Whole-package contract check for the live round package (C35).

Earlier contract tests validated either hand-written packages or real packages through a
partial checker that skipped unknown keys, so fields the server really emits
(``clubProfiles[*].sampleRefs``; ``sourceCoverage.map*`` on a CourseView course) drifted out
of ``mobile/contracts/live_round_package.schema.json`` unnoticed. These tests build the round
and course packages through the server service path in fixture mode and validate the full
response against the schema with Draft 2020-12.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ai_caddie.caddie import mobile_live
from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.courses import course_reference, courseview_core
from ai_caddie.llm import weather_context
from server_v2 import mobile
from tests.round_loop_authority import fixture_course_authority


SCHEMA_PATH = Path("mobile") / "contracts" / "live_round_package.schema.json"
CAPTURED_AT = "2026-10-25T08:00:00Z"
# A catalogue course the fixture player has never played, so the package is built from the
# cached CourseView lightweight map (the path that stamps sourceCoverage.map*).
UNPLAYED_GID = 900077
COURSE_DATA_BUILD = 266


def _schema_errors(payload: dict[str, object]) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    ]


def _provider_hole(number: int) -> dict[str, object]:
    # Public CourseView ``courseData`` field names; one route line per hole.
    return {
        "HoleNumber": number,
        "InfoMask": 4,
        "GreenRadii": [15, 15, 10, 9, 8, 9, 10, 14, 18, 19] * 3,
        "Line": [{
            "LineId": 30_883_700 + number,
            "LineCode": 3240,
            "CoordinateCount": 2,
            "Length": 320,
            "Flags": 1_073_741_824,
            "Points": [
                {"PointNumber": 1, "Latitude": 436_433_113 + number * 10_000, "Longitude": -1_455_147_649, "Closure": 0, "Flag": 0},
                {"PointNumber": 2, "Latitude": 436_388_613 + number * 10_000, "Longitude": -1_455_113_802, "Closure": 0, "Flag": 0},
            ],
        }],
        "Pars": [{"Par": 4, "Type": 0, "Sequence": 1, "PlayerType": 1}],
        "Hazards": [],
        "Handicaps": [{"Handicap": number, "TeeType": "NotSpecified", "PlayerType": 1}],
    }


def _install_cached_course_data(root: Path) -> None:
    """Write the release-bound lightweight map exactly as ``ensure_course_data`` caches it."""
    parsed = courseview_core.parse_course_data_json(
        {
            "BuildId": COURSE_DATA_BUILD,
            "GlobalLayoutId": UNPLAYED_GID,
            "Group": 0,
            "Holes": [_provider_hole(number) for number in range(1, 19)],
            "Tees": [{"TeeType": "Championship", "PlayerType": 1, "Rating": 72.0, "Slope": 130, "IsGarminEstimated": False}],
        },
        expected_build_id=COURSE_DATA_BUILD,
        expected_global_layout_id=UNPLAYED_GID,
        includes_hazard_lines=True,
    )
    path = courseview_core.course_data_cache_path(UNPLAYED_GID, COURSE_DATA_BUILD, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(parsed), encoding="utf-8")


class LiveRoundPackageWholeSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for target in (
            patch.object(mobile, "MOBILE_ROOT", self.root),
            patch.object(mobile, "ANNOTATION_ROOT", self.root / "annotations"),
            patch.object(mobile, "load_history_data_for_mode", return_value=(fixture_history_data(), "fixture")),
            patch.dict(mobile._PACKAGE_SINGLEFLIGHT, {}, clear=True),
            # Offline: a course package may ask Open-Meteo; production degrades to a missing snapshot.
            patch.object(weather_context, "_default_open_meteo_transport", side_effect=OSError("offline test")),
        ):
            target.start()
            self.addCleanup(target.stop)

    def test_round_package_matches_schema(self) -> None:
        with fixture_course_authority():
            response = mobile.build_mobile_round_package_response("900001", captured_at=CAPTURED_AT)
        payload = response.model_dump(mode="json", by_alias=True)

        # The fixture history has club shots, so the real profiles carry their sample refs.
        self.assertTrue(any(row.get("sampleRefs") for row in payload["clubProfiles"]))
        self.assertEqual([], _schema_errors(payload))

    def test_unplayed_course_package_matches_schema(self) -> None:
        _install_cached_course_data(self.root)
        release = {"release_version": COURSE_DATA_BUILD, "course_name": "Drift Fixture Golf", "holes": []}
        with (
            patch.object(course_reference, "courseview_release_info", return_value=release),
            patch.object(mobile_live, "_courseview_segment_resolver", return_value=("Drift Fixture Golf", 18)),
        ):
            response = mobile.build_mobile_course_package_response(
                UNPLAYED_GID,
                loops=[(UNPLAYED_GID, "front"), (UNPLAYED_GID, "back")],
                captured_at=CAPTURED_AT,
                include_event_cursor=False,
            )
        payload = response.model_dump(mode="json", by_alias=True)

        self.assertEqual(payload["sourceCoverage"].get("mapSource"), "courseData")
        self.assertTrue(any(row.get("sampleRefs") for row in payload["clubProfiles"]))
        self.assertEqual([], _schema_errors(payload))


if __name__ == "__main__":
    unittest.main()
