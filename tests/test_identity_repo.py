# tests/test_identity_repo.py
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server_v2 import identity_repo as repo
from server_v2.identity_models import Base, UserIdentity


class IdentityRepoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def test_create_family_with_owner_and_map_legacy(self):
        with self.Session() as s:
            family, owner = repo.create_family_with_owner(s, family_name="Horga", owner_display_name="我")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            s.commit()
            self.assertEqual(owner.role, "admin")
            self.assertEqual(family.owner_user_id, owner.id)
            self.assertEqual(repo.user_id_for_legacy_player(s, "me"), owner.id)

    def test_add_member_user(self):
        with self.Session() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            member = repo.add_user(s, family_id=family.id, display_name="老王", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_abcd1234", user_id=member.id)
            s.commit()
            self.assertEqual(member.role, "member")
            self.assertEqual(repo.user_id_for_legacy_player(s, "p_abcd1234"), member.id)
            self.assertIsNone(repo.user_id_for_legacy_player(s, "p_missing"))

    def test_get_user_by_apple_subject(self):
        with self.Session() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            s.add(UserIdentity(user_id=owner.id, provider="apple", subject="A.sub.123"))
            s.commit()
            found = repo.get_user_by_apple_subject(s, "A.sub.123")
            self.assertIsNotNone(found)
            self.assertEqual(found.id, owner.id)
            self.assertIsNone(repo.get_user_by_apple_subject(s, "unknown"))

    def test_provision_member_creates_user_legacy_map_and_apple_link(self):
        with self.Session() as s:
            family, _owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            member = repo.provision_member(
                s, family_id=family.id, display_name="Kid",
                pid="p_abcd1234", subject="sub-x", email="k@e.com",
            )
            s.commit()
            self.assertEqual(member.role, "member")
            self.assertEqual(member.family_id, family.id)
            self.assertEqual(member.display_name, "Kid")
            # the linchpin map row is created (map-only; no file registry)
            self.assertEqual(repo.legacy_player_for_user(s, member.id), "p_abcd1234")
            # the apple sub is linked to the new member
            self.assertEqual(repo.get_user_by_apple_subject(s, "sub-x").id, member.id)

    def test_provision_member_same_subject_again_raises_conflict(self):
        with self.Session() as s:
            family, _owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.provision_member(
                s, family_id=family.id, display_name="Kid",
                pid="p_abcd1234", subject="sub-x", email="k@e.com",
            )
            s.commit()
            with self.assertRaises(repo.IdentityConflictError):
                repo.provision_member(
                    s, family_id=family.id, display_name="Kid2",
                    pid="p_ffff0000", subject="sub-x", email="k2@e.com",
                )


if __name__ == "__main__":
    unittest.main()
