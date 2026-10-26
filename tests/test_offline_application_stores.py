"""Production default application stores must share the process's disposable root."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_caddie.connectors import snapshot, sync_lock
from ai_caddie.courses import course_reference
from ai_caddie.reports import reports
from ai_caddie.rounds import players
from server_v2 import db, main, reports as report_routes, sync_jobs
from tests.check_isolation import repository_artifacts


ROOT = Path(__file__).resolve().parents[1]


class OfflineApplicationStoreTests(unittest.TestCase):
    def setUp(self):
        self.cache = course_reference._courseview_dir().parents[1]
        before = repository_artifacts()
        self.addCleanup(lambda: self.assertEqual(repository_artifacts(), before))

    def assertDisposable(self, path):
        self.assertTrue(Path(path).resolve().is_relative_to(self.cache), str(path))

    def test_connector_status_defaults_are_disposable(self):
        self.assertDisposable(snapshot.ROOT / snapshot.SYNC_DIR)
        self.assertDisposable(snapshot.ROOT / snapshot.STATUS_FILE)
        path = snapshot.write_connector_status(state="no_data", detail="fixture", snapshot_id=None)
        self.assertDisposable(path)
        self.assertEqual(snapshot.read_connector_status()["state"], "no_data")

    def test_sync_lock_and_api_job_store_defaults_are_disposable(self):
        self.assertDisposable(sync_lock.sync_lock_path(ROOT))
        self.assertDisposable(main.SYNC_ROOT)
        self.assertDisposable(main._garmin_sync_jobs.root)
        self.assertDisposable(main._garmin_sync_jobs.directory)
        self.assertDisposable(sync_jobs.GarminSyncJobStore().directory)

    def test_report_store_and_api_defaults_are_disposable(self):
        self.assertDisposable(report_routes.REPORT_ROOT)
        self.assertDisposable(reports.report_store_file())
        self.assertDisposable(reports.evidence_root("fixture-member"))

    def test_player_registry_default_is_disposable(self):
        self.assertDisposable(players.ROOT)
        self.assertDisposable(players._registry_path(None))

    def test_identity_database_default_is_disposable_without_environment_override(self):
        self.assertDisposable(db.ROOT)
        with patch.dict(os.environ, {}, clear=True):
            self.assertDisposable(db.database_url().removeprefix("sqlite:///"))

    def test_explicit_application_roots_and_database_url_keep_their_scope(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = snapshot.write_connector_status(
                root=root, state="no_data", detail="explicit fixture", snapshot_id=None,
            )
            self.assertEqual(path, root / "data/sync/garmin_cn_status.json")
            self.assertEqual(snapshot.read_connector_status(root=root)["detail"], "explicit fixture")
            self.assertEqual(sync_lock.sync_lock_path(root), root / "data/sync/.garmin-sync.lock")
            self.assertEqual(sync_jobs.GarminSyncJobStore(root=root).root, root)
            self.assertEqual(reports.report_store_file(root), root / "data/reports/reports.jsonl")
            self.assertEqual(players._registry_path(root), root / "data/players/registry.json")
            with patch.dict(os.environ, {"AI_CADDIE_DATABASE_URL": "sqlite:///:memory:"}):
                self.assertEqual(db.database_url(), "sqlite:///:memory:")
