"""B4b-2: the server's round-hole tables are the iOS composition oracle.

`mobile/ios/AICaddieTests/Fixtures/b4b2_server_loop_tables.json` holds the real package route's
output for one 18-hole course: the canonical whole-course template (`G:front,G:back`), the two
one-half starts, and the `number -> (sourceGlobalId, sourceLocalHole, courseHoleNumber)` table
of every ordered / duplicate loop key. The Swift tests decode the template and require the
offline projection and turn composition to equal these tables. This test keeps the fixture in
lock-step with the server: regenerate with `REGENERATE_B4B2_FIXTURE=1`.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.courses import course_reference
from ai_caddie.history.history import HistoryData
from server_v2.main import app

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "mobile/ios/AICaddieTests/Fixtures/b4b2_server_loop_tables.json"
)
GLOBAL_ID = 55555
PARS = [4, 5, 3, 4, 3, 4, 4, 5, 4, 4, 5, 3, 4, 3, 4, 4, 5, 4]
ORDERS = [
    f"{GLOBAL_ID}:front,{GLOBAL_ID}:back",
    f"{GLOBAL_ID}:front,{GLOBAL_ID}:front",
    f"{GLOBAL_ID}:back,{GLOBAL_ID}:front",
    f"{GLOBAL_ID}:back,{GLOBAL_ID}:back",
    f"{GLOBAL_ID}:front",
    f"{GLOBAL_ID}:back",
]


def _coverage(global_id: int, local_hole: int) -> dict[str, object]:
    return {
        "schema": "ai-caddie-geometry-evidence-v1",
        "globalId": global_id,
        "localHole": local_hole,
        "coverage": "ready",
        "hasHazards": True,
        "hasMeshes": True,
        "evidence": [{"label": "geometry", "ref": f"gid{global_id}_h{local_hole:02d}"}],
        "missingData": [],
    }


def _fetch(client: TestClient, loops: str) -> dict:
    data = HistoryData(raw_rounds=[], rounds=[], shots=[])
    with (
        patch("server_v2.mobile.load_history_data_for_mode", return_value=(data, "local")),
        patch("ai_caddie.caddie.mobile_live.geometry_coverage_for_hole", side_effect=_coverage),
        patch.object(course_reference, "courseview_par", return_value=PARS),
    ):
        response = client.get(
            f"/api/v2/mobile/courses/{GLOBAL_ID}/package",
            params={"round_id": "b4b2-oracle", "tee_box": "blue", "loops": loops},
        )
    if response.status_code != 200:
        raise AssertionError(f"{loops}: {response.status_code} {response.text}")
    return response.json()


def build_fixture() -> dict:
    client = TestClient(app)
    packages = {loops: _fetch(client, loops) for loops in ORDERS}
    tables = {}
    for loops, package in packages.items():
        tables[package["loopKey"]] = {
            "roundLoops": package["roundLoops"],
            "holes": [
                {
                    "number": hole["number"],
                    "sourceGlobalId": hole["sourceGlobalId"],
                    "sourceLocalHole": hole["sourceLocalHole"],
                    "courseHoleNumber": hole["courseHoleNumber"],
                    "par": hole["par"],
                }
                for hole in package["holes"]
            ],
        }
    return {
        "schema": "ai-caddie-b4b2-loop-tables-v1",
        "globalId": GLOBAL_ID,
        # Packages are compared on their tables; `generatedAt` style volatile fields never matter.
        "wholeCourseTemplate": packages[ORDERS[0]],
        "frontHalf": packages[f"{GLOBAL_ID}:front"],
        "backHalf": packages[f"{GLOBAL_ID}:back"],
        "tables": tables,
    }


def _stable(value):
    """Drop per-request timestamps so the fixture comparison is about contract facts."""
    if isinstance(value, dict):
        return {
            key: _stable(item)
            for key, item in value.items()
            if key not in {"generatedAt", "preparedAt", "expiresAt", "capturedAt", "fetchedAt", "observedAt"}
        }
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


class B4b2LoopTablesFixtureTests(unittest.TestCase):
    def test_fixture_matches_the_server_route(self) -> None:
        current = build_fixture()
        if os.environ.get("REGENERATE_B4B2_FIXTURE") == "1":
            FIXTURE.write_text(json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        stored = json.loads(FIXTURE.read_text())
        self.assertEqual(_stable(stored["tables"]), _stable(current["tables"]))
        for key in ("wholeCourseTemplate", "frontHalf", "backHalf"):
            self.assertEqual(stored[key]["roundLoops"], current[key]["roundLoops"], key)
            self.assertEqual(stored[key]["loopKey"], current[key]["loopKey"], key)
            self.assertEqual(stored[key]["holes"], current[key]["holes"], key)

    def test_every_order_is_a_distinct_table(self) -> None:
        tables = json.loads(FIXTURE.read_text())["tables"]
        self.assertEqual(len(tables), len(ORDERS))
        back_front = tables[f"{GLOBAL_ID}:back+{GLOBAL_ID}:front"]["holes"]
        self.assertEqual([h["sourceLocalHole"] for h in back_front], list(range(10, 19)) + list(range(1, 10)))
        self.assertEqual([h["number"] for h in back_front], list(range(1, 19)))


if __name__ == "__main__":
    unittest.main()
