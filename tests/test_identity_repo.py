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

    def test_map_legacy_player_is_insert_only(self):
        # A legacy player id is the linchpin of a user's data isolation. map_legacy_player must be
        # insert-only: idempotent for the SAME user, but refuse to silently rebind to a DIFFERENT
        # user (which would hand one user's isolated data to another).
        with self.Session() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            member = repo.add_user(s, family_id=family.id, display_name="M", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_x", user_id=owner.id)
            s.commit()
            repo.map_legacy_player(s, legacy_player_id="p_x", user_id=owner.id)  # same user -> no-op
            self.assertEqual(repo.user_id_for_legacy_player(s, "p_x"), owner.id)
            with self.assertRaises(repo.PlayerIdInUseError):
                repo.map_legacy_player(s, legacy_player_id="p_x", user_id=member.id)  # rebind -> refused

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

    def test_list_family_users_pairs_each_user_with_its_legacy_id(self):
        with self.Session() as s:
            family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
            repo.map_legacy_player(s, legacy_player_id="me", user_id=owner.id)
            member = repo.add_user(s, family_id=family.id, display_name="Kid", role="member")
            repo.map_legacy_player(s, legacy_player_id="p_kid00001", user_id=member.id)
            no_map = repo.add_user(s, family_id=family.id, display_name="Mapless", role="member")
            # a user in ANOTHER family must NOT appear in this family's roster
            other_family, other_owner = repo.create_family_with_owner(s, family_name="G", owner_display_name="X")
            s.commit()
            rows = repo.list_family_users(s, family.id)
            by_id = {u.id: pid for u, pid in rows}
            self.assertEqual(set(by_id), {owner.id, member.id, no_map.id})
            self.assertEqual(by_id[owner.id], "me")
            self.assertEqual(by_id[member.id], "p_kid00001")
            self.assertIsNone(by_id[no_map.id])  # left-join: a map-only-less member still appears
            self.assertNotIn(other_owner.id, by_id)


if __name__ == "__main__":
    unittest.main()
