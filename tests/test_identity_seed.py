# tests/test_identity_seed.py
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from ai_caddie.rounds import players
from server_v2 import identity_repo as repo
from server_v2.identity_models import Base, Family, LegacyPlayerMap, User
from server_v2.identity_seed import seed_from_registry


class IdentitySeedTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patch = mock.patch.object(players, "ROOT", self.root)
        self._patch.start()
        players.create_player("老王", root=self.root)  # owner 'me' is implicit in the registry

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_seed_creates_owner_member_and_maps(self):
        with self.Session() as s:
            seed_from_registry(s, root=self.root)
            s.commit()
            self.assertEqual(s.execute(select(func.count()).select_from(Family)).scalar_one(), 1)
            self.assertEqual(s.execute(select(func.count()).select_from(User)).scalar_one(), 2)  # me + p_*
            me_user = repo.user_id_for_legacy_player(s, "me")
            self.assertIsNotNone(me_user)
            owner = s.get(User, me_user)
            self.assertEqual(owner.role, "admin")
            mapped = s.execute(select(func.count()).select_from(LegacyPlayerMap)).scalar_one()
            self.assertEqual(mapped, 2)

    def test_seed_is_idempotent(self):
        with self.Session() as s:
            seed_from_registry(s, root=self.root)
            seed_from_registry(s, root=self.root)  # second run must not duplicate
            s.commit()
            self.assertEqual(s.execute(select(func.count()).select_from(User)).scalar_one(), 2)
            self.assertEqual(s.execute(select(func.count()).select_from(Family)).scalar_one(), 1)
            self.assertEqual(s.execute(select(func.count()).select_from(LegacyPlayerMap)).scalar_one(), 2)


if __name__ == "__main__":
    unittest.main()
