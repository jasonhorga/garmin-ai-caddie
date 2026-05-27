from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_caddie.annotations import add_annotation
from ai_caddie.config import get_settings
from server_v2.main import app


class ServerV2HistoryDrilldownTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_history_drilldown_endpoint_resolves_fixture_shot_ref(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            response = TestClient(app).get("/api/v2/history/drilldown/900001:1:1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "ai-caddie-history-drilldown-v1")
        self.assertTrue(payload["found"])
        self.assertEqual(payload["refType"], "shot")
        self.assertEqual(payload["shot"]["club"], "8I")
        self.assertNotIn("schema_", payload)

    def test_history_drilldown_endpoint_returns_missing_contract(self) -> None:
        with patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}):
            get_settings.cache_clear()
            response = TestClient(app).get("/api/v2/history/drilldown/900404:9")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["found"])
        self.assertEqual(payload["ref"], "900404:9")
        self.assertEqual(payload["missingData"][0]["label"], "source_ref")

    def test_history_drilldown_endpoint_includes_manual_annotations_without_private_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            add_annotation(
                "shot",
                "900001:1:1",
                "club_correction",
                {"from": "8I", "to": "7I", "note": "wrong watch input"},
                root=root,
            )
            with (
                patch.dict(os.environ, {"AI_CADDIE_DATA_MODE": "fixture"}),
                patch("server_v2.history_drilldown.ANNOTATION_ROOT", root),
            ):
                get_settings.cache_clear()
                response = TestClient(app).get("/api/v2/history/drilldown/900001:1:1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["annotations"]), 1)
        self.assertEqual(len(payload["corrections"]), 1)
        self.assertEqual(payload["corrections"][0]["payload"]["to"], "7I")
        self.assertNotIn(tmp, response.text)


if __name__ == "__main__":
    unittest.main()
