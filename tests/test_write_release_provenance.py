import json
import tempfile
import unittest
import plistlib
import zipfile
from pathlib import Path
from ops.write_release_provenance import main


class ReleaseProvenanceWriterTests(unittest.TestCase):
    def test_artifact_only_allows_unconfigured_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            with zipfile.ZipFile(ipa, "w") as archive:
                archive.writestr("Payload/App.app/Info.plist", plistlib.dumps({"CFBundleVersion": "17"}))
            out = Path(tmp) / "release-provenance.json"
            self.assertEqual(main(["--ipa", str(ipa), "--commit", "a" * 40,
                                   "--workflow-run", "42", "--marketing-version", "1.0",
                                   "--output", str(out)]), 0)
            payload = json.loads(out.read_text())
            self.assertIsNone(payload["apiOriginHost"])
            self.assertIsNone(payload["backendRevision"])
            self.assertFalse(payload["backendRevisionVerified"])
            self.assertFalse(payload["uploadCompleted"])

    def test_upload_requires_origin_and_backend_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipa = Path(tmp) / "app.ipa"
            ipa.write_bytes(b"candidate")
            with self.assertRaises(SystemExit):
                main(["--ipa", str(ipa), "--commit", "a" * 40, "--workflow-run", "42",
                      "--marketing-version", "1.0", "--upload-to-testflight"])


if __name__ == "__main__":
    unittest.main()
