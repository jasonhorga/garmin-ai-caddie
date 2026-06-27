import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server_v2 import identity_repo as repo
from server_v2.identity_models import Base, UserIdentity


class AppleRepoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def test_legacy_player_for_user_roundtrips(self):
        with self.Session() as s:
            _f, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            s.commit()
            self.assertEqual(repo.legacy_player_for_user(s, owner.id), "me")
            self.assertIsNone(repo.legacy_player_for_user(s, "no_such_user"))

    def test_link_apple_identity_is_idempotent_and_resolvable(self):
        with self.Session() as s:
            _f, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.link_apple_identity(s, user_id=owner.id, subject="A.sub.1", email="a@b.c")
            repo.link_apple_identity(s, user_id=owner.id, subject="A.sub.1", email="a@b.c")  # idempotent
            s.commit()
            self.assertEqual(s.query(UserIdentity).count(), 1)
            self.assertEqual(repo.get_user_by_apple_subject(s, "A.sub.1").id, owner.id)

    def test_link_apple_identity_conflicts_on_different_user(self):
        with self.Session() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            other = repo.add_user(s, family_id=family.id, display_name="Other", role="member")
            repo.link_apple_identity(s, user_id=owner.id, subject="sub.x")
            with self.assertRaises(repo.IdentityConflictError):  # sub already owner's → can't re-point
                repo.link_apple_identity(s, user_id=other.id, subject="sub.x")
