# tests/test_db_engine.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import text

from server_v2 import db


class DatabaseUrlTests(unittest.TestCase):
    def test_explicit_env_url_wins(self):
        with mock.patch.dict(os.environ, {"AI_CADDIE_DATABASE_URL": "sqlite:///x.db"}):
            self.assertEqual(db.database_url(), "sqlite:///x.db")

    def test_default_is_sqlite_under_root(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            url = db.database_url()
        self.assertTrue(url.startswith("sqlite:///"))
        self.assertTrue(url.endswith("identity.db"))

    def test_session_scope_executes_and_commits(self):
        self.addCleanup(db.reset_engine_for_tests)  # unconditional, even if an assertion fails
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'identity.db'}"
            with mock.patch.dict(os.environ, {"AI_CADDIE_DATABASE_URL": url}):
                db.reset_engine_for_tests()
                with db.session_scope() as session:
                    value = session.execute(text("select 1")).scalar_one()
                self.assertEqual(value, 1)

    def test_session_scope_rolls_back_and_reraises(self):
        self.addCleanup(db.reset_engine_for_tests)
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'identity.db'}"
            with mock.patch.dict(os.environ, {"AI_CADDIE_DATABASE_URL": url}):
                db.reset_engine_for_tests()
                with db.session_scope() as session:  # committed setup table
                    session.execute(text("create table t (x integer)"))
                # an error inside the scope must roll the write back AND propagate
                with self.assertRaises(RuntimeError):
                    with db.session_scope() as session:
                        session.execute(text("insert into t values (1)"))
                        raise RuntimeError("boom")
                with db.session_scope() as session:
                    count = session.execute(text("select count(*) from t")).scalar_one()
                self.assertEqual(count, 0)  # the insert was rolled back


if __name__ == "__main__":
    unittest.main()
