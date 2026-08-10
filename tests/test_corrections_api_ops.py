"""复盘编辑端点接住新 op 形状:addShot(px/insertAfterShotId)、reorderShot(order)、
editField position 落库不被丢字段。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from ai_caddie.history import history as _history
from server_v2.main import app


class CorrectionsApiOpsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._p = mock.patch.object(_history, "ROOT", Path(self._tmp.name))
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self._tmp.cleanup()

    def test_addshot_op_accepted_and_persisted(self):
        c = TestClient(app)
        r = c.post(
            "/api/v2/history/rounds/42/corrections",
            json={"op": "addShot", "px": [360, 500], "club": "七号铁", "lie": "fairway", "insertAfterShotId": "s:42:1"},
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["stored"]["op"], "addShot")
        self.assertEqual(r.json()["stored"]["px"], [360, 500])
        self.assertEqual(r.json()["stored"]["club"], "七号铁")
        self.assertEqual(r.json()["stored"]["lie"], "fairway")
        self.assertEqual(r.json()["stored"]["insertAfterShotId"], "s:42:1")

    def test_replace_hole_snapshot_accepted_as_one_event(self):
        c = TestClient(app)
        r = c.post(
            "/api/v2/history/rounds/42/corrections",
            json={
                "op": "replaceHoleShots",
                "hole": 4,
                "geometryRevision": "geometry-r1",
                "manualPenalty": 1,
                "clientMutationId": "draft-save-1",
                "shots": [
                    {"id": "s:42:1", "start": [100, 900], "end": [300, 500], "order": 1},
                    {"id": "draft-2", "start": [300, 500], "end": [320, 200], "order": 2},
                ],
            },
        )

        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["stored"]["op"], "replaceHoleShots")
        self.assertEqual(r.json()["stored"]["hole"], 4)
        self.assertEqual(len(r.json()["stored"]["shots"]), 2)

    def test_replace_hole_snapshot_rejects_duplicate_ids(self):
        c = TestClient(app)
        r = c.post(
            "/api/v2/history/rounds/42/corrections",
            json={
                "op": "replaceHoleShots",
                "hole": 4,
                "manualPenalty": 0,
                "shots": [
                    {"id": "same", "start": [1, 2], "end": [3, 4]},
                    {"id": "same", "start": [3, 4], "end": [5, 6]},
                ],
            },
        )

        self.assertEqual(r.status_code, 400)

    def test_replace_hole_facts_accepts_only_geometry_independent_fields(self):
        c = TestClient(app)
        r = c.post(
            "/api/v2/history/rounds/42/corrections",
            json={
                "op": "replaceHoleFacts",
                "hole": 4,
                "manualPenalty": 1,
                "clientMutationId": "fact-save-1",
                "shots": [
                    {"id": "s:42:2", "club": "七号铁", "lie": "fairway"},
                    {"id": "s:42:1", "club": None, "lie": "teebox", "clubSource": "manual"},
                ],
            },
        )

        self.assertEqual(r.status_code, 201)
        stored = r.json()["stored"]
        self.assertEqual(stored["op"], "replaceHoleFacts")
        self.assertEqual([shot["id"] for shot in stored["shots"]], ["s:42:2", "s:42:1"])
        self.assertNotIn("geometryRevision", stored)
        self.assertFalse(any("start" in shot or "end" in shot for shot in stored["shots"]))

    def test_replace_hole_facts_rejects_pixel_fields(self):
        c = TestClient(app)
        r = c.post(
            "/api/v2/history/rounds/42/corrections",
            json={
                "op": "replaceHoleFacts",
                "hole": 4,
                "manualPenalty": 0,
                "shots": [{"id": "s:42:1", "club": "七号铁", "start": [1, 2]}],
            },
        )

        self.assertEqual(r.status_code, 400)

    def test_reorder_op_accepted(self):
        c = TestClient(app)
        r = c.post("/api/v2/history/rounds/42/corrections", json={"op": "reorderShot", "order": ["s:42:2", "s:42:1"]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["stored"]["order"], ["s:42:2", "s:42:1"])

    def test_edit_position_op_accepted(self):
        c = TestClient(app)
        r = c.post(
            "/api/v2/history/rounds/42/corrections",
            json={"op": "editField", "shotId": "s:42:1", "field": "position", "value": [400, 300]},
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["stored"]["field"], "position")
        self.assertEqual(r.json()["stored"]["value"], [400, 300])

    def test_addshot_without_px_rejected(self):
        c = TestClient(app)
        r = c.post("/api/v2/history/rounds/42/corrections", json={"op": "addShot", "club": "七号铁"})
        self.assertEqual(r.status_code, 400)

    def test_unknown_payload_field_is_rejected_instead_of_silently_dropped(self):
        c = TestClient(app)
        r = c.post(
            "/api/v2/history/rounds/42/corrections",
            json={"op": "addShot", "px": [1, 2], "clbu": "拼错的球杆字段"},
        )

        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
