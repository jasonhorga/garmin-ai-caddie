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
        self.assertEqual(r.json()["stored"]["insertAfterShotId"], "s:42:1")

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


if __name__ == "__main__":
    unittest.main()
