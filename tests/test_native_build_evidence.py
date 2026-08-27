from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ops.write_native_build_evidence import build_native_build_evidence, write_native_build_evidence


class NativeBuildEvidenceTests(unittest.TestCase):
    def test_writer_creates_readiness_compatible_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "native_build_evidence.json"
            payload = build_native_build_evidence(
                created_at="2026-05-28T10:20:30Z",
                commit="abc123",
                workflow_run_id="1001",
                ios_status="passed",
                ios_destination="platform=iOS Simulator,name=iPhone 16,OS=latest",
                watch_destination="platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
                ios_test_count=8,
                watch_test_count=4,
                ios_duration_seconds=12.3456,
            )
            write_native_build_evidence(output_path=output, payload=payload)

            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(saved["schema"], "ai-caddie-native-build-evidence-v1")
        self.assertEqual(saved["createdAt"], "2026-05-28T10:20:30Z")
        self.assertEqual(saved["commit"], "abc123")
        self.assertEqual(saved["workflowRunId"], "1001")
        self.assertEqual(saved["artifactName"], "native-build-evidence")
        self.assertEqual(saved["ios"]["scheme"], "AICaddie")
        self.assertEqual(saved["ios"]["status"], "passed")
        self.assertEqual(saved["ios"]["destination"], "platform=iOS Simulator,name=iPhone 16,OS=latest")
        self.assertEqual(saved["ios"]["testCount"], 8)
        self.assertEqual(saved["ios"]["durationSeconds"], 12.346)
        self.assertEqual(saved["watch"]["scheme"], "AICaddieWatch")
        self.assertEqual(saved["watch"]["status"], "skipped")

    def test_writer_accepts_explicit_passed_watch_status(self) -> None:
        payload = build_native_build_evidence(watch_status="passed")

        self.assertEqual(payload["watch"]["status"], "passed")

    def test_writer_defaults_unattested_ios_to_skipped(self) -> None:
        payload = build_native_build_evidence()

        self.assertEqual(payload["ios"]["status"], "skipped")

    def test_writer_preserves_failed_and_cancelled_mapping_from_producer(self) -> None:
        for status in ("failed", "cancelled", "skipped"):
            with self.subTest(status=status):
                payload = build_native_build_evidence(ios_status=status, watch_status=status)
                self.assertEqual(payload["ios"]["status"], status)
                self.assertEqual(payload["watch"]["status"], status)

    def test_writer_rejects_private_paths_and_secret_markers(self) -> None:
        with self.assertRaises(ValueError):
            build_native_build_evidence(
                commit="abc123",
                workflow_run_id="1001",
                ios_destination="/Users/private/Library/Developer/CoreSimulator",
                watch_destination="platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
            )

        with self.assertRaises(ValueError):
            build_native_build_evidence(
                commit="abc123-token",
                workflow_run_id="1001",
                ios_destination="platform=iOS Simulator,name=iPhone 16,OS=latest",
                watch_destination="platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
            )

        with self.assertRaises(ValueError):
            write_native_build_evidence(
                output_path=Path("/Users/private/native_build_evidence.json"),
                payload=build_native_build_evidence(
                    commit="abc123",
                    workflow_run_id="1001",
                    ios_destination="platform=iOS Simulator,name=iPhone 16,OS=latest",
                    watch_destination="platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
                ),
            )

    def test_writer_preserves_explicit_skipped_watch_status(self) -> None:
        payload = build_native_build_evidence(
            commit="abc123",
            workflow_run_id="1001",
            ios_destination="platform=iOS Simulator,name=iPhone 16,OS=latest",
            watch_destination="platform=watchOS Simulator,name=Apple Watch Series 10 (46mm),OS=latest",
            ios_status="passed",
            watch_status="skipped",
        )

        self.assertEqual(payload["ios"]["status"], "passed")
        self.assertEqual(payload["watch"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
