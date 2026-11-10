"""A new image migrates its identity database first, can step back one revision, and seeds idempotently.

The schema steps run the real Alembic command line as a child process against a
throw-away SQLite file (the deploy runs the same command before the API starts).
The seed runs through `server_v2.identity_seed.main` against that migrated file.
"""
import os
import sqlite3
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_caddie.rounds import players
from server_v2 import db, identity_seed

ROOT = Path(__file__).resolve().parents[2]
INITIAL = "0001_identity"
HEAD = "0002_legacy_map_user_unique"
SEEDED_TABLES = ("families", "users", "legacy_player_map")


def version(db_path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        return ",".join(r[0] for r in conn.execute("SELECT version_num FROM alembic_version"))


def alembic_inprocess(db_path: Path, *steps: tuple[str, ...]) -> list[str]:
    """Same migration scripts and env.py, driven through alembic.command without the ini's logging setup.

    Used by the boundary tests to avoid one interpreter start per step; the URL still comes from
    the product's own env-derived database_url() because the config leaves sqlalchemy.url empty.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    out = []
    for verb, target in steps:
        getattr(command, verb)(cfg, target)
        out.append(version(db_path))
    return out


def alembic(url: str, *steps: tuple[str, ...]) -> list[str]:
    """Run several Alembic CLI commands in one child process; return the version after each."""
    script = (
        "import sqlite3, sys\n"
        "from alembic.config import main\n"
        "path = sys.argv[1]\n"
        "for step in sys.argv[2:]:\n"
        "    main(argv=['-c', 'alembic.ini', *step.split()])\n"
        "    rows = sqlite3.connect(path).execute('SELECT version_num FROM alembic_version').fetchall()\n"
        "    print('VERSION=' + ','.join(r[0] for r in rows))\n"
    )
    env = {**os.environ, "AI_CADDIE_DATABASE_URL": url}
    result = subprocess.run(
        [sys.executable, "-c", script, url.removeprefix("sqlite:///"), *(" ".join(s) for s in steps)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(f"alembic exited {result.returncode}: {result.stderr[-2000:]}")
    return [line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("VERSION=")]


class Migrations(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db_path = self.root / "identity.db"
        self.url = f"sqlite:///{self.db_path}"
        for target in (
            patch.dict(os.environ, {"AI_CADDIE_DATABASE_URL": self.url}),
            patch.object(players, "ROOT", self.root),
            # The seed opens the process-wide engine; give it a fresh one for this file.
            patch.object(db, "_ENGINE", None),
            patch.object(db, "_SESSION_FACTORY", None),
        ):
            target.start()
            self.addCleanup(target.stop)
        self.addCleanup(self._dispose_engine)  # runs before the patches restore the old engine

    def _dispose_engine(self):
        if db._ENGINE is not None:
            db._ENGINE.dispose()

    def seed(self) -> str:
        out = StringIO()
        with redirect_stdout(out):
            identity_seed.main()
        return out.getvalue()

    def rows(self) -> dict[str, list[tuple]]:
        with sqlite3.connect(self.db_path) as conn:
            return {table: sorted(conn.execute(f"SELECT * FROM {table}").fetchall()) for table in SEEDED_TABLES}

    def legacy_map(self) -> dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            return dict(conn.execute("SELECT legacy_player_id, user_id FROM legacy_player_map"))

    def test_upgrade_downgrade_seed_idempotent(self):
        """S-25 [main]: an empty database upgrades to head, steps back one revision, upgrades again, and seeding twice leaves the same rows"""
        self.assertFalse(self.db_path.exists())
        versions = alembic(self.url, ("upgrade", "head"), ("downgrade", "-1"), ("upgrade", "head"))
        self.assertEqual(versions, [HEAD, INITIAL, HEAD])

        players.create_player("Member", root=self.root)
        first_out = self.seed()
        first = self.rows()
        self.assertIn("seeded 2 legacy players", first_out)
        self.assertEqual(len(first["families"]), 1)
        self.assertEqual(len(first["users"]), 2)
        self.assertEqual(set(self.legacy_map()), {players.OWNER_ID, *(p["id"] for p in players.load_registry(root=self.root)["players"])})

        second_out = self.seed()
        self.assertIn("seeded 2 legacy players", second_out)
        self.assertEqual(self.rows(), first, "a second seed changed identity rows")

    def test_seed_on_seeded_database_adds_only_new_players(self):
        """S-25: seeding an already-seeded database keeps existing users and adds only players new to the registry"""
        alembic_inprocess(self.db_path, ("upgrade", "head"))
        self.seed()
        before = self.legacy_map()
        self.assertEqual(list(before), [players.OWNER_ID])

        added = players.create_player("Late joiner", root=self.root)
        self.seed()
        after = self.legacy_map()
        self.assertEqual(set(after), {players.OWNER_ID, added["id"]})
        self.assertEqual(after[players.OWNER_ID], before[players.OWNER_ID], "the owner was re-created")
        self.assertEqual(len(self.rows()["families"]), 1)
        self.assertEqual(len(set(after.values())), 2, "two legacy players share one user")

    def test_downgrade_then_reupgrade_keeps_seeded_rows(self):
        """S-25: stepping a seeded database back one revision and upgrading again keeps every identity row"""
        alembic_inprocess(self.db_path, ("upgrade", "head"))
        players.create_player("Member", root=self.root)
        self.seed()
        seeded = self.rows()

        versions = alembic_inprocess(self.db_path, ("downgrade", "-1"), ("upgrade", "head"))
        self.assertEqual(versions, [INITIAL, HEAD])
        self.assertEqual(self.rows(), seeded)

        self.seed()  # the app-start seed after the re-upgrade is still a no-op
        self.assertEqual(self.rows(), seeded)

    def test_head_rejects_one_user_mapped_to_two_players(self):
        """S-25: at head one user maps to at most one legacy player; one revision down that rule is gone"""
        alembic_inprocess(self.db_path, ("upgrade", "head"))
        self.seed()
        owner_user = self.legacy_map()[players.OWNER_ID]
        with sqlite3.connect(self.db_path) as conn, self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO legacy_player_map VALUES (?, ?)", ("p_extra", owner_user))

        self.assertEqual(alembic_inprocess(self.db_path, ("downgrade", "-1")), [INITIAL])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO legacy_player_map VALUES (?, ?)", ("p_extra", owner_user))
        self.assertEqual(len(self.legacy_map()), 2)


if __name__ == "__main__":
    unittest.main()
