"""B4b-2 §6: the shared round-identity cases every validator must agree on.

JSON Schema cannot express the cross-field identity (``loopKey == roundLoops``, each hole on its
table row). That invariant is owned by one validation rule set implemented three times — the
server (`ai_caddie.caddie.round_loops.validate_round_identity`), the iPhone
(`LiveRoundPackage.validatedRoundIdentity`) and the Watch (`WatchCoursePackage` decoding) — and
all three are tested against the same cases file generated here. Regenerate with
``REGENERATE_ROUND_IDENTITY_CASES=1``.
"""

from __future__ import annotations

import copy
import json
import os
import unittest
from pathlib import Path

from ai_caddie.caddie.round_loops import RoundLoopError, validate_round_identity

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "mobile/contracts/fixtures/round_identity_cases.json"
COPIES = (
    ROOT / "mobile/ios/AICaddieTests/Fixtures/round_identity_cases.json",
    ROOT / "mobile/ios/AICaddieWatchTests/round_identity_cases.json",
)
SCHEMA = "ai-caddie-live-round-package-v2"


def _hole(number: int, gid: int, local: int, course: int) -> dict:
    return {
        "number": number,
        "par": 4,
        "yards": 400,
        "geometryCoverage": "ready",
        "sourceGlobalId": gid,
        "sourceLocalHole": local,
        "courseHoleNumber": course,
    }


def _package(loops: list[tuple[int, str]]) -> dict:
    table, holes = [], []
    for index, (gid, half) in enumerate(loops):
        start, source = 1 + 9 * index, 10 if half == "back" else 1
        table.append({"globalId": gid, "half": half, "roundStartHole": start,
                      "sourceStartHole": source, "holeCount": 9})
        for offset in range(9):
            local = source + offset
            holes.append(_hole(start + offset, gid, local, start + offset if half == "all" else local))
    return {
        "schema": SCHEMA,
        "roundId": "identity-case",
        "course": {"globalId": loops[0][0] if loops else 31795, "name": "Identity Case", "teeBox": "blue"},
        "holes": holes,
        "roundLoops": table,
        "loopKey": "+".join(f"{gid}:{half}" for gid, half in loops),
    }


def build_cases() -> dict:
    valid = {
        "front": _package([(31795, "front")]),
        "back": _package([(31795, "back")]),
        "front_back": _package([(31795, "front"), (31795, "back")]),
        "back_front": _package([(31795, "back"), (31795, "front")]),
        "back_back": _package([(31795, "back"), (31795, "back")]),
        "loop_all": _package([(31870, "all")]),
        "two_loops_all": _package([(31870, "all"), (31871, "all")]),
        "no_holes": {**_package([]), "holes": [], "roundLoops": [], "loopKey": ""},
    }
    base = valid["front"]
    two = valid["front_back"]

    def mutate(source: dict, change) -> dict:
        package = copy.deepcopy(source)
        change(package)
        return package

    invalid = {
        # The four mutations from the owner review (JSON Schema accepted each one).
        "loopkey_contradicts_loops": mutate(base, lambda p: p.update(loopKey="31795:back")),
        "hole_local_contradicts_row": mutate(base, lambda p: p["holes"][0].update(sourceLocalHole=2)),
        "hole_number_breaks_sequence": mutate(base, lambda p: p["holes"][0].update(number=9)),
        "loop_course_contradicts_holes": mutate(
            base, lambda p: (p["roundLoops"][0].update(globalId=99999), p.update(loopKey="99999:front"))
        ),
        "course_hole_number_contradicts_row": mutate(base, lambda p: p["holes"][2].update(courseHoleNumber=12)),
        "round_start_not_1": mutate(base, lambda p: p["roundLoops"][0].update(roundStartHole=7)),
        "second_start_not_10": mutate(two, lambda p: p["roundLoops"][1].update(roundStartHole=1)),
        "hole_count_not_9": mutate(base, lambda p: p["roundLoops"][0].update(holeCount=1)),
        "back_source_start_1": mutate(
            valid["back"], lambda p: p["roundLoops"][0].update(sourceStartHole=1)
        ),
        "loopkey_order_swapped": mutate(two, lambda p: p.update(loopKey="31795:back+31795:front")),
        "loopkey_comma": mutate(two, lambda p: p.update(loopKey="31795:front,31795:back")),
        "duplicate_hole": mutate(base, lambda p: p["holes"].append(copy.deepcopy(p["holes"][0]))),
        "missing_hole": mutate(base, lambda p: p["holes"].pop()),
        "three_loops": mutate(
            two,
            lambda p: (
                p["roundLoops"].append({"globalId": 31795, "half": "front", "roundStartHole": 19,
                                        "sourceStartHole": 1, "holeCount": 9}),
                p.update(loopKey=p["loopKey"] + "+31795:front"),
            ),
        ),
        "holes_without_loops": mutate(base, lambda p: p.update(roundLoops=[], loopKey="")),
        "loop_without_holes": mutate(base, lambda p: p.update(holes=[])),
        "schema_v1": mutate(base, lambda p: p.update(schema="ai-caddie-live-round-package-v1")),
    }
    return {
        "schema": "ai-caddie-round-identity-cases-v1",
        "valid": valid,
        "invalid": invalid,
    }


def _server_accepts(package: dict) -> bool:
    if package.get("schema") != SCHEMA:
        return False
    holes = package.get("holes") or []
    if not holes:
        return package.get("roundLoops") == [] and package.get("loopKey") == ""
    try:
        validate_round_identity(package.get("roundLoops"), package.get("loopKey"), holes)
    except RoundLoopError:
        return False
    return True


class RoundIdentityCasesTests(unittest.TestCase):
    def test_cases_file_is_current_and_copied_to_every_client(self) -> None:
        current = json.dumps(build_cases(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        if os.environ.get("REGENERATE_ROUND_IDENTITY_CASES") == "1":
            for path in (CANONICAL, *COPIES):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(current, encoding="utf-8")
        self.assertEqual(CANONICAL.read_text(encoding="utf-8"), current)
        for copy_path in COPIES:
            self.assertEqual(copy_path.read_text(encoding="utf-8"), current, copy_path)

    def test_server_validator_agrees_with_every_case(self) -> None:
        cases = json.loads(CANONICAL.read_text(encoding="utf-8"))
        for name, package in cases["valid"].items():
            self.assertTrue(_server_accepts(package), name)
        for name, package in cases["invalid"].items():
            self.assertFalse(_server_accepts(package), name)

    def test_schema_documents_that_identity_is_owned_by_the_shared_validators(self) -> None:
        schema = json.loads((ROOT / "mobile/contracts/live_round_package.schema.json").read_text())
        self.assertIn("round_identity_cases.json", schema.get("description", ""))


if __name__ == "__main__":
    unittest.main()
