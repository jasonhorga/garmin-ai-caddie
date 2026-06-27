import unittest


class DatabaseDepsImportableTests(unittest.TestCase):
    def test_core_db_libraries_import(self):
        import alembic  # noqa: F401
        import psycopg  # noqa: F401
        import sqlalchemy  # noqa: F401
        self.assertTrue(sqlalchemy.__version__.startswith("2."))


if __name__ == "__main__":
    unittest.main()
