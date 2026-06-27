# tests/test_identity_migration.py
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from server_v2.identity_models import Base

REPO_ROOT = Path(__file__).resolve().parents[1]


class IdentityMigrationTests(unittest.TestCase):
    def test_upgrade_head_creates_all_model_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "m.db"
            url = f"sqlite:///{db_path}"
            cfg = Config(str(REPO_ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
            cfg.set_main_option("sqlalchemy.url", url)
            command.upgrade(cfg, "head")

            tables = set(inspect(create_engine(url, future=True)).get_table_names())
            model_tables = set(Base.metadata.tables) | {"alembic_version"}
            self.assertTrue(model_tables.issubset(tables), model_tables - tables)


if __name__ == "__main__":
    unittest.main()
