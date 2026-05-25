from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest

from ops.export_snapshot import export_snapshot
from ops.import_snapshot import import_snapshot


class SnapshotImportExportTests(unittest.TestCase):
    def test_export_import_excludes_secrets_and_restores_data(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data" / "scorecards").mkdir(parents=True)
            (source / "data" / "shots").mkdir()
            (source / "data" / "snapshots").mkdir()
            (source / "data" / "sync").mkdir()
            (source / "data" / "summary.json").write_text("[]", encoding="utf-8")
            (source / "data" / "scorecards" / "1.json").write_text("{}", encoding="utf-8")
            (source / "data" / "shots" / "1.json").write_text("{}", encoding="utf-8")
            (source / "data" / "snapshots" / "manifest.json").write_text("{}", encoding="utf-8")
            (source / "data" / "sync" / "status.json").write_text("{}", encoding="utf-8")
            (source / ".env").write_text("SECRET=1", encoding="utf-8")
            (source / ".garmin_tokens").mkdir()
            (source / ".garmin_tokens" / "web_cookie.txt").write_text("cookie", encoding="utf-8")
            (source / "clubs.json").write_text('{"secret":"club"}', encoding="utf-8")

            tarball = Path(tmp) / "snapshot.tar.gz"
            export_snapshot(source_root=source, output_path=tarball)
            with tarfile.open(tarball, "r:gz") as archive:
                names = sorted(archive.getnames())

            target = Path(tmp) / "target"
            import_snapshot(tarball, target_root=target)

            self.assertIn("data/summary.json", names)
            self.assertIn("data/scorecards/1.json", names)
            self.assertIn("data/shots/1.json", names)
            self.assertIn("data/snapshots/manifest.json", names)
            self.assertIn("data/sync/status.json", names)
            self.assertNotIn(".env", names)
            self.assertNotIn(".garmin_tokens/web_cookie.txt", names)
            self.assertNotIn("clubs.json", names)
            self.assertEqual((target / "data" / "summary.json").read_text(encoding="utf-8"), "[]")
            self.assertFalse((target / ".env").exists())
            self.assertFalse((target / ".garmin_tokens").exists())
            self.assertFalse((target / "clubs.json").exists())

    def test_export_can_include_clubs_when_explicit(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data").mkdir()
            (source / "clubs.json").write_text('{"Driver":"1D"}', encoding="utf-8")
            tarball = Path(tmp) / "snapshot.tar.gz"

            export_snapshot(source_root=source, output_path=tarball, include_clubs=True)
            with tarfile.open(tarball, "r:gz") as archive:
                names = archive.getnames()

        self.assertIn("clubs.json", names)

    def test_import_rejects_unsafe_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            tarball = Path(tmp) / "bad.tar.gz"
            payload = Path(tmp) / "payload.txt"
            payload.write_text("bad", encoding="utf-8")
            with tarfile.open(tarball, "w:gz") as archive:
                archive.add(payload, arcname="../escape.txt")

            with self.assertRaises(ValueError):
                import_snapshot(tarball, target_root=Path(tmp) / "target")


if __name__ == "__main__":
    unittest.main()
