# tests/test_app_boots_with_db.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from server_v2 import db


class AppBootsWithDbTests(unittest.TestCase):
    def test_health_ok_and_identity_tables_exist_on_sqlite(self):
        self.addCleanup(db.reset_engine_for_tests)  # unconditional, even if an assertion fails
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
                from server_v2.main import app  # imported under env
                with TestClient(app) as client:  # context = lifespan runs
                    self.assertEqual(client.get("/api/v2/health").status_code, 200)
                    from sqlalchemy import inspect
                    tables = set(inspect(db.get_engine()).get_table_names())
                    self.assertIn("users", tables)


if __name__ == "__main__":
    unittest.main()
