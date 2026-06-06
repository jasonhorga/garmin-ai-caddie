from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ops.smoke_local_private_data import build_smoke_evidence, assert_secret_free


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict[str, object]:
        return self._payload


class FakeClient:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def get(self, path: str) -> FakeResponse:
        self.paths.append(path)
        if path == "/api/v2/history/rounds":
            return FakeResponse({"schema": "rounds", "groups": [{"rounds": [{"id": "round-1"}]}]})
        if path == "/api/v2/history/rounds/round-1":
            return FakeResponse({"schema": "detail", "holeDetails": []})
        return FakeResponse({"schema": path.strip("/").replace("/", "-"), "count": 1})


class LocalPrivateSmokeTests(unittest.TestCase):
    def test_build_smoke_evidence_checks_local_history_endpoints(self) -> None:
        client = FakeClient()
        evidence = build_smoke_evidence(client, base_url="testclient")

        self.assertEqual(evidence["schema"], "ai-caddie-local-private-smoke-evidence-v1")
        self.assertEqual(evidence["dataMode"], "local")
        self.assertIn("GET /api/v2/health", evidence["checks"])
        self.assertIn("GET /api/v2/history/rounds/round-1", evidence["checks"])
        self.assertEqual(evidence["roundDetailChecked"], True)
        self.assertIn("/api/v2/sync/status", client.paths)

    def test_assert_secret_free_rejects_private_terms(self) -> None:
        with self.assertRaises(AssertionError):
            assert_secret_free({"path": "/home/private/.garmin_tokens/token.json"})

    def test_main_writes_evidence_file(self) -> None:
        from ops import smoke_local_private_data as smoke

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "smoke.json"
            client = FakeClient()
            smoke.write_smoke_evidence(client=client, output=output, base_url="testclient")
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], "ai-caddie-local-private-smoke-evidence-v1")
        self.assertNotIn("/home/", json.dumps(payload).lower())


if __name__ == "__main__":
    unittest.main()
