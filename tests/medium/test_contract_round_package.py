"""The round package the phone downloads is a valid contract document (test-plan 6.2).

The response comes from the real HTTP route in fixture mode, so a field the
server emits but the shared schema does not describe turns this test red.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from ai_caddie.core.fixtures import fixture_history_data
from ai_caddie.llm import weather_context
from server_v2 import course_install, mobile
from server_v2 import main as server_main
from server_v2.main import app
from tests.round_loop_authority import fixture_course_authority

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SCHEMA = "mobile/contracts/live_round_package.schema.json"
ROUND_ID = "900001"
# A package download leases its round as active for 30 minutes. Left in the process, that lease
# keeps nearby_work_blocked() true and every later background backfill waits on it forever.
ACTIVE_ROUND_STATE = (
    (server_main, ("_ACTIVE_ROUNDS", "_ACTIVE_COURSES", "_ACTIVE_EVENT_TIMES", "_ACTIVE_START_TIMES",
                   "_ROUND_START_CACHE", "_ACTIVE_EVENT_DEVICES", "_ACTIVE_SELECTIONS")),
    (course_install, ("_CURRENT_COURSE_IDS",)),
)


class RoundPackageRouteContractTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for target in (
            patch.object(mobile, "MOBILE_ROOT", root),
            patch.object(mobile, "ANNOTATION_ROOT", root / "annotations"),
            patch.object(mobile, "load_history_data_for_mode", return_value=(fixture_history_data(), "fixture")),
            patch.dict(mobile._PACKAGE_SINGLEFLIGHT, {}, clear=True),
            # Offline: the package degrades to a missing weather snapshot instead of calling Open-Meteo.
            patch.object(weather_context, "_default_open_meteo_transport", side_effect=OSError("offline test")),
            patch.object(server_main, "_ACTIVE_PACKAGED_ROUNDS", set()),
            *(patch.dict(getattr(module, name), clear=True) for module, names in ACTIVE_ROUND_STATE for name in names),
        ):
            target.start()
            self.addCleanup(target.stop)

    def test_round_package_route_response_passes_schema(self):
        """S-06: GET /api/v2/mobile/rounds/{rid}/package returns a body the shared package schema accepts."""
        with fixture_course_authority():
            response = TestClient(app).get(f"/api/v2/mobile/rounds/{ROUND_ID}/package",
                                           params={"captured_at": "2026-10-25T08:00:00Z"})
        self.assertEqual(response.status_code, 200, response.text[:500])
        payload = response.json()
        self.assertEqual(payload["roundId"], ROUND_ID)
        self.assertTrue(payload["holes"])

        schema = json.loads((ROOT / PACKAGE_SCHEMA).read_text(encoding="utf-8"))
        errors = [f"{'/'.join(map(str, error.absolute_path))}: {error.message}"
                  for error in Draft202012Validator(schema).iter_errors(payload)]
        self.assertEqual([], errors)
