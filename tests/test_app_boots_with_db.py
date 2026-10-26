# tests/test_app_boots_with_db.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from server_v2 import db

REPO_ROOT = Path(__file__).resolve().parents[1]


class AppBootsWithDbTests(unittest.TestCase):
    def test_health_ok_after_migrate_then_boot_on_sqlite(self):
        """Deploy flow: `alembic upgrade head` (the sole schema authority) then serve."""
        self.addCleanup(db.reset_engine_for_tests)
        # Alembic's fileConfig would disable existing loggers and replace suite handlers.
        # This test checks schema/health, so keep process logging outside its scope.
        self.enterContext(mock.patch("logging.config.fileConfig"))
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'identity.db'}"
            env = {
                "AI_CADDIE_DATABASE_URL": url,
                "AI_CADDIE_DATA_MODE": "fixture",
                "AI_CADDIE_SECURITY_PROFILE": "",
                "AI_CADDIE_ADMIN_TOKEN": "",
            }
            with mock.patch.dict(os.environ, env):
                db.reset_engine_for_tests()
                # 1) migrate — what start_api.sh runs before uvicorn (sole schema authority)
                cfg = Config(str(REPO_ROOT / "alembic.ini"))
                cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
                cfg.set_main_option("sqlalchemy.url", url)
                command.upgrade(cfg, "head")
                # 2) boot the app and confirm it serves + the migrated schema is present
                from server_v2 import main

                # Lifespan does not stop its daemon warmers when TestClient exits. In particular,
                # stats warming can consume a later test's geometry mock observations. Isolate
                # unrelated startup work and restore every patch through addCleanup.
                self.enterContext(mock.patch.object(main, "warm_stats_cache_in_background"))
                self.enterContext(mock.patch.object(main, "_prepare_recent_bg"))
                self.enterContext(mock.patch.object(main.course_install, "resume_pending_jobs"))
                self.enterContext(mock.patch.object(main._garmin_sync_jobs, "start"))
                self.enterContext(mock.patch.object(main, "configure_request_timing_logging"))
                with TestClient(main.app) as client:  # context = lifespan runs
                    self.assertEqual(client.get("/api/v2/health").status_code, 200)
                    tables = set(inspect(db.get_engine()).get_table_names())
                    self.assertIn("users", tables)


if __name__ == "__main__":
    unittest.main()
