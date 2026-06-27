# tests/test_identity_models.py
import unittest

from sqlalchemy import create_engine, inspect

from server_v2.identity_models import Base


class IdentityModelsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(self.engine)
        self.inspector = inspect(self.engine)

    def test_all_identity_tables_exist(self):
        expected = {
            "families", "users", "user_identities", "legacy_player_map",
            "devices", "sessions", "token_revocations", "access_audit", "round_acl",
        }
        self.assertTrue(expected.issubset(set(self.inspector.get_table_names())))

    def test_user_identity_unique_provider_subject(self):
        uniques = self.inspector.get_unique_constraints("user_identities")
        cols = {tuple(u["column_names"]) for u in uniques}
        self.assertIn(("provider", "subject"), cols)

    def test_session_has_token_hash(self):
        cols = {c["name"] for c in self.inspector.get_columns("sessions")}
        self.assertIn("token_hash", cols)


if __name__ == "__main__":
    unittest.main()
