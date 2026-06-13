from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest

from ops.export_snapshot import export_snapshot
from ops.import_snapshot import import_snapshot


class SnapshotImportExportTests(unittest.TestCase):
    def test_export_snapshot_records_portable_manifest_without_private_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data" / "scorecards").mkdir(parents=True)
            (source / "data" / "scorecards" / "1.json").write_text("{}", encoding="utf-8")
            tarball = Path(tmp) / "snapshot.tar.gz"

            manifest = export_snapshot(source_root=source, output_path=tarball)

        self.assertEqual(manifest["schema"], "ai-caddie-export-snapshot-v1")
        self.assertGreater(manifest["sizeBytes"], 0)
        self.assertEqual(manifest["fileCount"], 1)
        self.assertEqual(manifest["includedRoots"], ["data"])
        self.assertTrue(manifest["secretFree"])
        self.assertNotIn("/home/", json.dumps(manifest).lower())
        self.assertNotIn(".garmin_tokens", json.dumps(manifest).lower())

    def test_export_import_excludes_secrets_and_restores_data(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data" / "scorecards").mkdir(parents=True)
            (source / "data" / "shots").mkdir()
            (source / "data" / "snapshots").mkdir()
            (source / "data" / "sync").mkdir()
            (source / "data" / "annotations").mkdir()
            (source / "data" / "media").mkdir()
            (source / "data" / "weather").mkdir()
            (source / "data" / "reports").mkdir()
            (source / "data" / "decision_audits").mkdir()
            (source / "output" / "prodgeometry_hazards").mkdir(parents=True)
            (source / "output" / "prodgeometry").mkdir(parents=True)
            (source / "output" / "prodgeometry_overlay").mkdir(parents=True)
            (source / "data" / "summary.json").write_text("[]", encoding="utf-8")
            (source / "data" / "scorecards" / "1.json").write_text("{}", encoding="utf-8")
            (source / "data" / "shots" / "1.json").write_text("{}", encoding="utf-8")
            (source / "data" / "snapshots" / "manifest.json").write_text("{}", encoding="utf-8")
            (source / "data" / "sync" / "status.json").write_text("{}", encoding="utf-8")
            (source / "data" / "annotations" / "annotations.jsonl").write_text('{"kind":"issue_tag"}\n', encoding="utf-8")
            (source / "data" / "media" / "media_index.jsonl").write_text('{"mediaKind":"photo"}\n', encoding="utf-8")
            (source / "data" / "weather" / "weather_snapshots.jsonl").write_text('{"state":"ready"}\n', encoding="utf-8")
            (source / "data" / "reports" / "reports.jsonl").write_text('{"kind":"round"}\n', encoding="utf-8")
            (source / "data" / "decision_audits" / "decision_audits.jsonl").write_text(
                '{"classification":"execution"}\n',
                encoding="utf-8",
            )
            (source / "output" / "prodgeometry_hazards" / "gid31795_h04_hazards.json").write_text(
                '{"hazards":[]}',
                encoding="utf-8",
            )
            (source / "output" / "prodgeometry" / "gid31795_h04_meshes.json").write_text(
                '{"meshes":[]}',
                encoding="utf-8",
            )
            (source / "output" / "prodgeometry_overlay" / "debug.png").write_text(
                "not portable snapshot data",
                encoding="utf-8",
            )
            (source / ".env").write_text("SECRET=1", encoding="utf-8")
            (source / ".garmin_tokens").mkdir()
            (source / ".garmin_tokens" / "web_cookie.txt").write_text("cookie", encoding="utf-8")
            (source / "data" / "scorecards" / "secret-link.json").symlink_to(source / ".env")
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
            self.assertIn("data/annotations/annotations.jsonl", names)
            self.assertIn("data/media/media_index.jsonl", names)
            self.assertIn("data/weather/weather_snapshots.jsonl", names)
            self.assertIn("data/reports/reports.jsonl", names)
            self.assertIn("data/decision_audits/decision_audits.jsonl", names)
            self.assertIn("output/prodgeometry_hazards/gid31795_h04_hazards.json", names)
            self.assertIn("output/prodgeometry/gid31795_h04_meshes.json", names)
            self.assertNotIn("output/prodgeometry_overlay/debug.png", names)
            self.assertNotIn(".env", names)
            self.assertNotIn(".garmin_tokens/web_cookie.txt", names)
            self.assertNotIn("data/scorecards/secret-link.json", names)
            self.assertNotIn("clubs.json", names)
            self.assertEqual((target / "data" / "summary.json").read_text(encoding="utf-8"), "[]")
            self.assertEqual((target / "data" / "annotations" / "annotations.jsonl").read_text(encoding="utf-8"), '{"kind":"issue_tag"}\n')
            self.assertEqual((target / "data" / "media" / "media_index.jsonl").read_text(encoding="utf-8"), '{"mediaKind":"photo"}\n')
            self.assertEqual((target / "data" / "weather" / "weather_snapshots.jsonl").read_text(encoding="utf-8"), '{"state":"ready"}\n')
            self.assertEqual((target / "data" / "reports" / "reports.jsonl").read_text(encoding="utf-8"), '{"kind":"round"}\n')
            self.assertEqual(
                (target / "data" / "decision_audits" / "decision_audits.jsonl").read_text(encoding="utf-8"),
                '{"classification":"execution"}\n',
            )
            self.assertEqual(
                (target / "output" / "prodgeometry_hazards" / "gid31795_h04_hazards.json").read_text(encoding="utf-8"),
                '{"hazards":[]}',
            )
            self.assertEqual(
                (target / "output" / "prodgeometry" / "gid31795_h04_meshes.json").read_text(encoding="utf-8"),
                '{"meshes":[]}',
            )
            self.assertFalse((target / "output" / "prodgeometry_overlay" / "debug.png").exists())
            self.assertFalse((target / ".env").exists())
            self.assertFalse((target / ".garmin_tokens").exists())
            self.assertFalse((target / "clubs.json").exists())

    def test_export_includes_player_data_roots_and_skips_symlinks(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "data" / "players" / "p_friend" / "scorecards").mkdir(parents=True)
            (source / "data" / "players" / "p_friend" / "scorecards" / "900.json").write_text(
                "{}", encoding="utf-8"
            )
            (source / "data" / "players" / "p_friend" / "shots").mkdir()
            (source / "data" / "players" / "p_friend" / "shots" / "900.json").write_text(
                "{}", encoding="utf-8"
            )
            (source / ".env").write_text("SECRET=1", encoding="utf-8")
            (source / "data" / "players" / "p_friend" / "secret-link.json").symlink_to(
                source / ".env"
            )

            tarball = Path(tmp) / "snapshot.tar.gz"
            export_snapshot(source_root=source, output_path=tarball)
            with tarfile.open(tarball, "r:gz") as archive:
                names = sorted(archive.getnames())

            target = Path(tmp) / "target"
            import_snapshot(tarball, target_root=target)

            self.assertIn("data/players/p_friend/scorecards/900.json", names)
            self.assertIn("data/players/p_friend/shots/900.json", names)
            self.assertNotIn("data/players/p_friend/secret-link.json", names)
            self.assertEqual(
                (target / "data" / "players" / "p_friend" / "scorecards" / "900.json").read_text(
                    encoding="utf-8"
                ),
                "{}",
            )

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

    def test_import_rejects_unsupported_output_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            tarball = Path(tmp) / "bad-output.tar.gz"
            payload = Path(tmp) / "payload.json"
            payload.write_text("{}", encoding="utf-8")
            with tarfile.open(tarball, "w:gz") as archive:
                archive.add(payload, arcname="output/prodgeometry_overlay/debug.json")

            with self.assertRaises(ValueError):
                import_snapshot(tarball, target_root=Path(tmp) / "target")


if __name__ == "__main__":
    unittest.main()
