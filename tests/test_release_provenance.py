import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from ops.write_release_provenance import main


class ReleaseProvenanceTests(unittest.TestCase):
    def test_artifact_manifest_allows_offline_candidate_without_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            with ZipFile(ipa, "w") as archive:
                archive.writestr("Payload/App.app/Info.plist", b"invalid")
            output = Path(tmp) / "release-provenance.json"
            code = main(["--ipa", str(ipa), "--commit", "a" * 40, "--workflow-run", "42", "--marketing-version", "1.0", "--build-number", "7", "--output", str(output)])
            self.assertEqual(code, 0)
            payload = json.loads(output.read_text())
            self.assertFalse(payload["uploadToTestflight"])
            self.assertIsNone(payload["apiOriginHost"])
            self.assertIsNone(payload["backendRevision"])
            self.assertRegex(payload["ipaSha256"], r"^[0-9a-f]{64}$")

    def test_upload_writes_secret_free_sidecar_with_origin_and_backend_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            with ZipFile(ipa, "w") as archive:
                archive.writestr(
                    "Payload/App.app/Info.plist",
                    b"<?xml version=\"1.0\" encoding=\"UTF-8\"?><plist version=\"1.0\"><dict><key>CFBundleVersion</key><string>17</string></dict></plist>",
                )
            output = Path(tmp) / "release-provenance.json"
            with patch.dict(os.environ, {"GITHUB_SHA": "a" * 40}, clear=False):
                code = main(
                    [
                        "--ipa",
                        str(ipa),
                        "--commit",
                        "a" * 40,
                        "--workflow-run",
                        "42",
                        "--marketing-version",
                        "1.0",
                        "--build-number",
                        "17",
                        "--api-origin",
                        "https://api.example.test",
                        "--backend-revision",
                        "b" * 40,
                        "--upload-to-testflight",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(output.read_text())
            self.assertTrue(payload["uploadToTestflight"])
            self.assertEqual(payload["apiOriginHost"], "api.example.test")
            self.assertEqual(payload["backendRevision"], "b" * 40)
            self.assertEqual(payload["buildNumber"], "17")

    def test_upload_requires_backend_revision_and_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            ipa.write_bytes(b"ipa")
            with self.assertRaises(SystemExit):
                main(["--ipa", str(ipa), "--commit", "a" * 40, "--workflow-run", "42", "--marketing-version", "1.0", "--build-number", "7", "--upload-to-testflight"])

    def test_upload_requires_github_sha_even_when_cli_commit_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            ipa.write_bytes(b"ipa")
            with patch.dict(os.environ, {"GITHUB_SHA": ""}, clear=False):
                with self.assertRaisesRegex(SystemExit, "GITHUB_SHA"):
                    main(
                        [
                            "--ipa",
                            str(ipa),
                            "--commit",
                            "a" * 40,
                            "--workflow-run",
                            "42",
                            "--marketing-version",
                            "1.0",
                            "--build-number",
                            "7",
                            "--api-origin",
                            "https://api.example.test",
                            "--backend-revision",
                            "b" * 40,
                            "--upload-to-testflight",
                        ]
                    )

    def test_upload_rejects_commit_that_differs_from_github_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            ipa.write_bytes(b"ipa")
            with patch.dict(os.environ, {"GITHUB_SHA": "c" * 40}, clear=False):
                with self.assertRaisesRegex(SystemExit, "does not match GITHUB_SHA"):
                    main(
                        [
                            "--ipa",
                            str(ipa),
                            "--commit",
                            "a" * 40,
                            "--workflow-run",
                            "42",
                            "--marketing-version",
                            "1.0",
                            "--build-number",
                            "7",
                            "--api-origin",
                            "https://api.example.test",
                            "--backend-revision",
                            "b" * 40,
                            "--upload-to-testflight",
                        ]
                    )

    def test_upload_rejects_private_or_local_origins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            ipa.write_bytes(b"ipa")
            with self.assertRaises(SystemExit):
                main([
                    "--ipa",
                    str(ipa),
                    "--commit",
                    "a" * 40,
                    "--workflow-run",
                    "42",
                    "--marketing-version",
                    "1.0",
                    "--build-number",
                    "7",
                    "--api-origin",
                    "https://localhost",
                    "--backend-revision",
                    "b" * 40,
                    "--upload-to-testflight",
                ])


if __name__ == "__main__":
    unittest.main()
