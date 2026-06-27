import tempfile, unittest
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from server_v2.identity_models import Base, LegacyPlayerMap, User, Family

REPO_ROOT = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


class Migration0002Tests(unittest.TestCase):
    def test_user_id_is_unique_in_legacy_map(self):
        engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(Family(id="f1", name="F")); s.add(User(id="u1", family_id="f1", display_name="A"))
            s.add(LegacyPlayerMap(legacy_player_id="me", user_id="u1"))
            s.add(LegacyPlayerMap(legacy_player_id="p_x", user_id="u1"))  # same user → must fail
            with self.assertRaises(IntegrityError):
                s.commit()

    def test_alembic_head_enforces_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'm.db'}"
            cfg = Config(str(REPO_ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
            cfg.set_main_option("sqlalchemy.url", url)
            command.upgrade(cfg, "head")
            eng = create_engine(url, future=True)
            with Session(eng) as s:
                s.add(Family(id="f1", name="F")); s.add(User(id="u1", family_id="f1", display_name="A"))
                s.add(LegacyPlayerMap(legacy_player_id="me", user_id="u1"))
                s.add(LegacyPlayerMap(legacy_player_id="p_x", user_id="u1"))
                with self.assertRaises(IntegrityError):
                    s.commit()

    def test_upgrade_fails_fast_on_preexisting_duplicate_user_id(self):
        # A real DB upgraded from 0001 may already hold duplicate user_id rows (the pre-0002
        # repo keyed only by legacy_player_id). The 0002 preflight must fail fast with a clear,
        # actionable RuntimeError naming the offending user_id — not a raw IntegrityError.
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'm.db'}"
            cfg = _cfg(url)
            command.upgrade(cfg, "0001_identity")  # stop BEFORE the UNIQUE constraint
            eng = create_engine(url, future=True)
            with Session(eng) as s:
                s.add(Family(id="f1", name="F"))
                s.add(User(id="u1", family_id="f1", display_name="A"))
                s.commit()  # the user must exist before the FK-referencing maps
                s.add(LegacyPlayerMap(legacy_player_id="me", user_id="u1"))
                s.add(LegacyPlayerMap(legacy_player_id="p_x", user_id="u1"))  # dup user_id, allowed at 0001
                s.commit()
            with self.assertRaises(RuntimeError) as ctx:
                command.upgrade(cfg, "head")  # runs 0002 → preflight trips
            self.assertIn("duplicate user_id", str(ctx.exception))
            self.assertIn("u1", str(ctx.exception))
