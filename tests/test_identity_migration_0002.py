import tempfile, unittest
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from server_v2.identity_models import Base, LegacyPlayerMap, User, Family

REPO_ROOT = Path(__file__).resolve().parents[1]


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
