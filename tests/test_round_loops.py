"""B4b-2 round loops: the strict parser, the invariant, both routes and past-round authority."""

from __future__ import annotations

import copy
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_caddie.caddie import mobile_live
from ai_caddie.caddie.round_loops import (
    CourseShape,
    RoundLoopError,
    parse_round_loops,
    resolve_round_loops,
    round_loop_key,
    round_loops_table,
    validate_round_identity,
)
from ai_caddie.history.history import HistoryData
from server_v2.main import app
from server_v2.models import LiveRoundPackageResponse

MALFORMED_LISTS = ("55555:front,", ",55555:front", "55555:front,,55555:back")


def _holes(loops: list[tuple[int, str]]) -> list[dict[str, object]]:
    """The contract table's holes for ``loops``: the only valid hole list for that order."""
    holes: list[dict[str, object]] = []
    for row in round_loops_table(loops):
        for offset in range(9):
            number = row["roundStartHole"] + offset
            local = row["sourceStartHole"] + offset
            holes.append({
                "number": number,
                "sourceGlobalId": row["globalId"],
                "sourceLocalHole": local,
                "courseHoleNumber": number if row["half"] == "all" else local,
                "par": 4,
                "geometryCoverage": "missing",
            })
    return holes


def _identity(loops: list[tuple[int, str]]) -> tuple[list[dict[str, object]], str, list[dict[str, object]]]:
    return round_loops_table(loops), round_loop_key(loops), _holes(loops)


def _package_payload(loops: list[tuple[int, str]]) -> dict[str, object]:
    table, key, holes = _identity(loops)
    return {
        "schema": "ai-caddie-live-round-package-v2",
        "roundId": "round-loops",
        "dataMode": "fixture",
        "sourceCoverage": {},
        "missingData": [],
        "playerProfile": {},
        "course": {"globalId": loops[0][0]},
        "roundLoops": table,
        "loopKey": key,
        "holes": holes,
        "geometryCoverage": {},
        "caddieContextSeeds": [],
        "weatherSnapshot": {},
        "clubProfiles": [],
        "caddieDecisionEndpoint": "/api/v2/caddie/decision",
        "offlinePackageStatus": {},
        "eventCursor": {},
        "recentHistory": {},
        "cachedCaddieRules": {},
        "generatedAt": "2026-09-29T00:00:00Z",
    }


class ParseRoundLoopsTests(unittest.TestCase):
    def test_valid_orders_and_duplicates_are_accepted(self) -> None:
        self.assertEqual(parse_round_loops("55555:front", path_global_id=55555), [(55555, "front")])
        self.assertEqual(
            parse_round_loops("55555:back,55555:back", path_global_id=55555),
            [(55555, "back"), (55555, "back")],
        )
        self.assertEqual(
            parse_round_loops(" 31796:all , 31794:all ", path_global_id=31796),
            [(31796, "all"), (31794, "all")],
        )

    def test_malformed_input_is_rejected_never_normalized(self) -> None:
        for raw in (
            *MALFORMED_LISTS,
            "",
            None,
            ",",
            " , ",
            "55555:front, ,55555:back",
            "55555",
            "55555:",
            ":front",
            "abc:front",
            "-55555:front",
            "0:front",
            "٥٥٥٥٥:front",  # Arabic-Indic digits are not an ASCII globalId
            "５５５５５:front",  # fullwidth digits
            "55555:middle",
            "55555:FRONT",
            "55555:front:back",
            "55555:front,55555:back,55555:front",
            "31796:front",  # the path course must be the first loop
        ):
            with self.assertRaises(RoundLoopError, msg=repr(raw)):
                parse_round_loops(raw, path_global_id=55555)


class ResolveRoundLoopsTests(unittest.TestCase):
    SHAPES = {
        55555: CourseShape(holes=18, venue="links"),
        31796: CourseShape(holes=9, venue="players"),
        31794: CourseShape(holes=9, venue="players"),
        31797: CourseShape(holes=9, venue="elsewhere"),
    }

    def resolve(self, loops: list[tuple[int, str]]) -> list[tuple[int, str]]:
        return resolve_round_loops(loops, self.SHAPES.get)

    def test_proven_orders_resolve(self) -> None:
        for loops in (
            [(55555, "back"), (55555, "front")],
            [(55555, "front"), (55555, "front")],
            [(31796, "all"), (31794, "all")],
            [(31796, "all"), (31796, "all")],
        ):
            self.assertEqual(self.resolve(loops), loops)

    def test_unprovable_orders_are_rejected(self) -> None:
        for loops in (
            [(55555, "all")],  # an 18-hole course is requested as halves
            [(31796, "front")],  # a 9-hole loop has no halves
            [(66666, "front")],  # unknown course
            [(31796, "all"), (31797, "all")],  # cross-venue
            [(31796, "all"), (55555, "front")],  # cross-venue, mixed shapes
            [],
            [(55555, "front")] * 3,
        ):
            with self.assertRaises(RoundLoopError, msg=str(loops)):
                self.resolve(loops)


class ValidateRoundIdentityTests(unittest.TestCase):
    def assert_rejected(self, table: object, key: object, holes: object) -> None:
        with self.assertRaises(RoundLoopError):
            validate_round_identity(table, key, holes)
        payload = _package_payload([(55555, "front"), (55555, "back")])
        payload.update({"roundLoops": table, "loopKey": key, "holes": holes})
        with self.assertRaises(ValidationError):
            LiveRoundPackageResponse(**payload)

    def test_every_valid_order_passes(self) -> None:
        for loops in (
            [(55555, "front")],
            [(55555, "back")],
            [(55555, "back"), (55555, "front")],
            [(55555, "back"), (55555, "back")],
            [(31796, "all"), (31794, "all")],
        ):
            validate_round_identity(*_identity(loops))
            package = LiveRoundPackageResponse(**_package_payload(loops))
            self.assertEqual(package.loopKey, round_loop_key(loops))

    def test_each_invariant_is_enforced(self) -> None:
        loops = [(55555, "back"), (55555, "front")]

        table, key, holes = _identity(loops)
        table[1]["roundStartHole"] = 1
        self.assert_rejected(table, key, holes)  # starts must be 1 then 10

        table, key, holes = _identity(loops)
        table[0], table[1] = table[1], table[0]
        self.assert_rejected(table, key, holes)  # ordered: second loop listed first

        table, key, holes = _identity(loops)
        table[0]["holeCount"] = 8
        self.assert_rejected(table, key, holes)

        table, key, holes = _identity(loops)
        table[0]["sourceStartHole"] = 1  # back must start on physical hole 10
        self.assert_rejected(table, key, holes)

        table, key, holes = _identity([(31796, "all")])
        table[0]["sourceStartHole"] = 10  # all starts on physical hole 1
        self.assert_rejected(table, key, holes)

        table, _, holes = _identity(loops)
        for bad_key in ("55555:front+55555:back", "55555:back,55555:front", "55555:back", "", None):
            self.assert_rejected(table, bad_key, holes)

        table, key, holes = _identity(loops)
        holes[1] = dict(holes[0])  # hole 1 twice, hole 2 missing
        self.assert_rejected(table, key, holes)

        table, key, holes = _identity(loops)
        self.assert_rejected(table, key, holes[:-1])  # a loop missing a hole

        table, key, holes = _identity(loops)
        self.assert_rejected(table, key, [*holes, {**holes[0], "number": 19}])  # a hole beyond the table

        for field, value in (
            ("sourceGlobalId", 31796),
            ("sourceLocalHole", 1),
            ("courseHoleNumber", 1),
        ):
            table, key, holes = _identity(loops)
            holes[0][field] = value  # round hole 1 is physical back-nine hole 10
            self.assert_rejected(table, key, holes)

        for field in ("sourceGlobalId", "sourceLocalHole", "courseHoleNumber"):
            table, key, holes = _identity(loops)
            del holes[0][field]  # missing identity is never filled from `number`
            self.assert_rejected(table, key, holes)

        table, key, holes = _identity(loops)
        extra = copy.deepcopy(table[0])
        extra["roundStartHole"] = 19
        self.assert_rejected([*table, extra], f"{key}+55555:back", holes)  # more than two loops

        self.assert_rejected([], "", _holes(loops))  # holes without a table

    def test_the_response_model_rejects_a_named_loop_without_holes_and_unknown_fields(self) -> None:
        degraded = _package_payload([(55555, "front")])
        degraded.update({"holes": [], "roundLoops": [], "loopKey": ""})
        LiveRoundPackageResponse(**degraded)
        for update in (
            {"loopKey": "55555:front"},
            {"roundLoops": round_loops_table([(55555, "front")])},
        ):
            with self.assertRaises(ValidationError):
                LiveRoundPackageResponse(**{**degraded, **update})
        with self.assertRaises(ValidationError):
            LiveRoundPackageResponse(**{**_package_payload([(55555, "front")]), "nine": "front"})


class RoundLoopJsonSchemaTests(unittest.TestCase):
    """The shared JSON contract carries the same shape rules as the server model."""

    def setUp(self) -> None:
        import json
        from pathlib import Path

        from jsonschema import Draft202012Validator

        schema = json.loads(Path("mobile/contracts/live_round_package.schema.json").read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(schema)
        # The iOS fixture is a contract-valid 9-hole package (31795:front).
        self.base = json.loads(
            Path("mobile/ios/AICaddie/Fixtures/live_round_package.fixture.json").read_text(encoding="utf-8")
        )

    def errors(self, package: dict[str, object]) -> list[str]:
        return [error.message for error in self.validator.iter_errors(package)]

    def test_the_fixture_is_accepted(self) -> None:
        self.assertEqual(self.errors(self.base), [])
        self.assertEqual(self.base["loopKey"], "31795:front")

    def test_invalid_loop_shapes_are_rejected(self) -> None:
        one = copy.deepcopy(self.base["roundLoops"][0])
        two = {**one, "roundStartHole": 10}
        mutations = {
            "holeCount 8": {"roundLoops": [{**one, "holeCount": 8}]},
            "first loop starts on 10": {"roundLoops": [{**one, "roundStartHole": 10}]},
            "second loop starts on 1": {"roundLoops": [one, {**one}]},
            "front starts on physical 10": {"roundLoops": [{**one, "sourceStartHole": 10}]},
            "back starts on physical 1": {"roundLoops": [{**one, "half": "back"}]},
            "all starts on physical 10": {"roundLoops": [{**one, "half": "all", "sourceStartHole": 10}]},
            "three loops": {"roundLoops": [one, two, {**two, "roundStartHole": 19}]},
            "two loops with nine holes": {"roundLoops": [one, two], "loopKey": "31795:front+31795:front"},
            "no loops with holes": {"roundLoops": [], "loopKey": ""},
            "loop key with comma": {"loopKey": "31795:front,31795:back"},
            "loop key with bad half": {"loopKey": "31795:middle"},
            "loop key with zero id": {"loopKey": "0:front"},
            "loop key with trailing plus": {"loopKey": "31795:front+"},
            "no holes but a loop": {"holes": []},
        }
        for label, update in mutations.items():
            package = {**copy.deepcopy(self.base), **update}
            self.assertTrue(self.errors(package), label)
        # An 18-hole package isolates the ordered-start rule: 1 then 10 is accepted, 1 then 1 is not.
        eighteen = copy.deepcopy(self.base)
        eighteen["holes"] += [{**hole, "number": hole["number"] + 9} for hole in eighteen["holes"]]
        eighteen["loopKey"] = "31795:front+31795:front"
        eighteen["roundLoops"] = [one, two]
        self.assertEqual(self.errors(eighteen), [])
        eighteen["roundLoops"] = [one, {**one}]
        self.assertTrue(self.errors(eighteen))
        for field in ("sourceGlobalId", "sourceLocalHole", "courseHoleNumber"):
            package = copy.deepcopy(self.base)
            del package["holes"][0][field]
            self.assertTrue(self.errors(package), f"missing {field}")
            package["holes"][0][field] = 0
            self.assertTrue(self.errors(package), f"zero {field}")

    def test_the_explicit_degraded_package_is_accepted(self) -> None:
        package = {**copy.deepcopy(self.base), "holes": [], "roundLoops": [], "loopKey": ""}
        self.assertEqual(self.errors(package), [])


def _coverage(global_id: int, local_hole: int, **_kwargs: object) -> dict[str, object]:
    return {
        "schema": "ai-caddie-geometry-evidence-v1",
        "globalId": int(global_id),
        "localHole": int(local_hole),
        "coverage": "missing",
        "hasHazards": False,
        "hasMeshes": False,
        "evidence": [],
        "missingData": [],
    }


# CourseView releases used by the route tests: (clean name, hole count).
_RELEASES = {
    55555: ("Fixture Links", 18),
    31796: ("The Players Club ~ C", 9),
    31794: ("The Players Club ~ A", 9),
    31797: ("Harbour Club ~ A", 9),
}


def _release_resolver(global_id: int, *, allow_fetch: bool = False):
    return _RELEASES.get(int(global_id))


def _courseview_par(global_id: int, *_args: object, **_kwargs: object):
    release = _RELEASES.get(int(global_id))
    return [4] * release[1] if release else None


class RoundLoopRouteTests(unittest.TestCase):
    """Both routes share one strict parser and resolver: nothing unproven gets a loopKey."""

    def setUp(self) -> None:
        from ai_caddie.courses import course_reference

        self.client = TestClient(app)
        self._install_dir = TemporaryDirectory()
        self.addCleanup(self._install_dir.cleanup)
        empty = HistoryData(raw_rounds=[], rounds=[], shots=[])
        for active in (
            patch.dict(os.environ, {"AI_CADDIE_COURSE_INSTALL_DIR": self._install_dir.name}),
            patch("server_v2.mobile.load_history_data_for_mode", return_value=(empty, "fixture")),
            patch.object(mobile_live, "geometry_coverage_for_hole", side_effect=_coverage),
            patch.object(mobile_live, "_courseview_segment_resolver", side_effect=_release_resolver),
            patch.object(course_reference, "courseview_par", side_effect=_courseview_par),
        ):
            active.start()
            self.addCleanup(active.stop)

    def package(self, global_id: int, loops: str):
        return self.client.get(
            f"/api/v2/mobile/courses/{global_id}/package",
            params={"round_id": "round-loop-route", "tee_box": "blue", "loops": loops},
        )

    def install_status(self, global_id: int, loops: str):
        return self.client.get(
            f"/api/v2/courses/{global_id}/install/status",
            params={"tee_box": "blue", "loops": loops},
        )

    def test_proven_orders_build_their_exact_identity(self) -> None:
        for global_id, loops in (
            (55555, "55555:back,55555:front"),
            (55555, "55555:front,55555:front"),
            (31796, "31796:all,31794:all"),
        ):
            response = self.package(global_id, loops)
            self.assertEqual(response.status_code, 200, f"{loops}: {response.text[:300]}")
            body = response.json()
            self.assertEqual(body["loopKey"], loops.replace(",", "+"))
            validate_round_identity(body["roundLoops"], body["loopKey"], body["holes"])

    def test_invalid_orders_are_422_on_both_routes(self) -> None:
        cases = [
            *((55555, loops) for loops in MALFORMED_LISTS),
            (55555, "55555:all"),  # wrong half: 18-hole course
            (31796, "31796:front"),  # wrong half: 9-hole loop
            (31796, "31796:all,31796:back"),
            (66666, "66666:front"),  # unknown course
            (66666, "66666:all"),
            (31796, "31796:all,31797:all"),  # cross-venue
            (55555, "55555:front,31796:all"),  # cross-venue, mixed shapes
        ]
        for global_id, loops in cases:
            with self.subTest(route="package", loops=loops):
                response = self.package(global_id, loops)
                self.assertEqual(response.status_code, 422, response.text[:300])
            with self.subTest(route="install-status", loops=loops):
                response = self.install_status(global_id, loops)
                self.assertEqual(response.status_code, 422, response.text[:300])

    def test_install_status_is_404_until_enqueued_then_200(self) -> None:
        from server_v2 import course_install
        from server_v2 import main as server_main

        self.assertEqual(self.install_status(55555, "55555:back,55555:front").status_code, 404)
        with patch.object(course_install, "_launch"):
            course_install.enqueue(
                global_id=55555,
                tee_box="blue",
                loop_key="55555:back+55555:front",
                player_id=server_main.OWNER_ID,
                refs=[{"globalId": 55555, "localHole": 10, "displayHole": 1}],
                requested={55555: [10]},
                ready={},
            )
        response = self.install_status(55555, "55555:back,55555:front")
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assertEqual(response.json()["loopKey"], "55555:back+55555:front")
        # The same course in another order is still a distinct, never-enqueued job.
        self.assertEqual(self.install_status(55555, "55555:front,55555:back").status_code, 404)
        # A malformed alias of the enqueued order is rejected, not matched.
        self.assertEqual(self.install_status(55555, "55555:back,,55555:front").status_code, 422)


def _round(round_id: str, global_id: int, *, holes: int, back_global_id: int | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "id": round_id,
        "ids": [round_id],
        "date": "2026-09-01",
        "course": "黑骑士",
        "courseKey": "black_knight",
        "globalId": global_id,
        "holesCompleted": holes,
        "strokes": 4 * holes,
        "par": 4 * holes,
        "holes": [{"number": number, "par": 4, "strokes": 4} for number in range(1, holes + 1)],
    }
    if back_global_id is not None:
        row["backNineGlobalCourseId"] = back_global_id
    return row


class PastRoundLoopAuthorityTests(unittest.TestCase):
    """A past round's loopKey rests on durable metadata only, cold (no CourseView cache) or warm."""

    def build(self, row: dict[str, object], releases: dict[int, int]) -> dict[str, object]:
        data = HistoryData(raw_rounds=[], rounds=[row], shots=[])

        def resolver(global_id: int, *, allow_fetch: bool = False):
            holes = releases.get(int(global_id))
            return (f"Course {global_id}", holes) if holes else None

        with (
            patch.object(mobile_live, "_courseview_segment_resolver", side_effect=resolver),
            patch.object(mobile_live, "geometry_coverage_for_hole", side_effect=_coverage),
        ):
            package = mobile_live.build_live_round_package(
                str(row["id"]), data=data, data_mode="local", allow_weather_fetch=False,
            )
            stamped = mobile_live.apply_past_round_loop_identity(package)
        # Whatever the outcome, it is a valid wire package.
        LiveRoundPackageResponse(**stamped)
        for hole in stamped["holes"]:
            self.assertNotIn("_sourceIdentityProven", hole)
        return stamped

    def assert_degraded(self, package: dict[str, object]) -> None:
        self.assertEqual(package["holes"], [])
        self.assertEqual(package["roundLoops"], [])
        self.assertEqual(package["loopKey"], "")
        self.assertIn("round_loop_authority", {row["label"] for row in package["missingData"]})

    def physical(self, package: dict[str, object]) -> list[tuple[int, int, int, int]]:
        return [
            (h["number"], h["sourceGlobalId"], h["sourceLocalHole"], h["courseHoleNumber"])
            for h in package["holes"]
        ]

    def test_two_course_round_is_identical_cold_and_warm(self) -> None:
        row = _round("a-plus-b", 31794, holes=18, back_global_id=31795)
        cold = self.build(row, {})
        warm = self.build(row, {31794: 9, 31795: 9})
        for package in (cold, warm):
            self.assertEqual(package["loopKey"], "31794:all+31795:all")
            self.assertEqual(
                self.physical(package),
                [(n, 31794, n, n) for n in range(1, 10)] + [(n, 31795, n - 9, n) for n in range(10, 19)],
            )
        self.assertEqual(cold["roundLoops"], warm["roundLoops"])

    def test_one_loop_played_twice_with_garmin_back_id_is_identical_cold_and_warm(self) -> None:
        row = _round("a-plus-a", 31796, holes=18, back_global_id=31796)
        cold = self.build(row, {})
        warm = self.build(row, {31796: 9})
        for package in (cold, warm):
            self.assertEqual(package["loopKey"], "31796:all+31796:all")
        self.assertEqual(self.physical(cold), self.physical(warm))
        self.assertEqual(cold["roundLoops"], warm["roundLoops"])

    def test_one_loop_played_twice_without_back_id_degrades_cold_never_front(self) -> None:
        row = _round("a-twice", 31796, holes=18)
        cold = self.build(row, {})
        self.assert_degraded(cold)
        warm = self.build(row, {31796: 9})
        self.assertEqual(warm["loopKey"], "31796:all+31796:all")
        self.assertEqual(
            self.physical(warm),
            [(n, 31796, n, n) for n in range(1, 10)] + [(n, 31796, n - 9, n) for n in range(10, 19)],
        )

    def test_an_eighteen_hole_round_of_one_course_is_front_then_back(self) -> None:
        row = _round("full-18", 55555, holes=18)
        package = self.build(row, {55555: 18})
        self.assertEqual(package["loopKey"], "55555:front+55555:back")
        self.assertEqual(self.physical(package), [(n, 55555, n, n) for n in range(1, 19)])
        # Without the release, holes 10–18 could be the 9-hole loop again: no guess.
        self.assert_degraded(self.build(row, {}))

    def test_a_lone_nine_needs_authority(self) -> None:
        row = _round("lone-nine", 31796, holes=9)
        self.assert_degraded(self.build(row, {}))
        self.assertEqual(self.build(row, {31796: 9})["loopKey"], "31796:all")
        self.assertEqual(self.build(row, {31796: 18})["loopKey"], "31796:front")

    def test_identity_is_never_filled_from_number(self) -> None:
        # A round without any course id has no physical identity at all.
        row = _round("no-course", 0, holes=18)
        row.pop("globalId")
        self.assert_degraded(self.build(row, {}))

        nine = [
            {"number": n, "sourceGlobalId": 31796, "sourceLocalHole": n} for n in range(1, 10)
        ]
        for field in ("sourceGlobalId", "sourceLocalHole"):
            holes = copy.deepcopy(nine)
            holes[3][field] = None
            with self.assertRaises(RoundLoopError):
                mobile_live.derive_past_round_loops(holes)
        # The course-start path drops a hole without identity rather than inventing one.
        course = mobile_live._course_holes_with_identity(
            {"holes": [{"number": 1, "sourceGlobalId": 31796, "sourceLocalHole": None}]}, 31796,
        )
        self.assertEqual(course["holes"], [])

    def test_the_round_route_serves_the_degraded_package_through_the_model(self) -> None:
        row = _round("a-twice-route", 31796, holes=18)
        data = HistoryData(raw_rounds=[], rounds=[row], shots=[])
        with (
            patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "local")),
            patch.object(mobile_live, "_courseview_segment_resolver", return_value=None),
            patch.object(mobile_live, "geometry_coverage_for_hole", side_effect=_coverage),
        ):
            response = TestClient(app).get("/api/v2/mobile/rounds/a-twice-route/package")
        self.assertEqual(response.status_code, 200, response.text[:300])
        self.assert_degraded(response.json())


if __name__ == "__main__":
    unittest.main()
