# Phase 1a — Database Foundation & Identity Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up PostgreSQL + a SQLAlchemy identity/tenancy schema + a repository layer, and backfill the legacy `me`/`p_*` players into it — **purely additive**, changing no request-handling behavior.

**Architecture:** A new sync SQLAlchemy 2.0 layer (`server_v2/db.py` + `server_v2/identity_models.py` + `server_v2/identity_repo.py`), schema-managed by Alembic. `AI_CADDIE_DATABASE_URL` selects the backend: **SQLite by default** (dev / CI / containers with no Postgres) and **PostgreSQL** in `docker-compose.yml`. All models use portable column types so the same migration runs on both. A one-shot seeder maps the existing JSON player registry → `families`/`users`/`legacy_player_map`. Nothing in the existing request path reads the DB yet (that is Phase 1b/1c).

**Tech Stack:** SQLAlchemy 2.0 (sync), Alembic, psycopg 3 (Postgres driver), SQLite (stdlib, tests/dev), FastAPI lifespan, uv, unittest.

**Scope boundary:** This is plan **1 of 3** for Phase 1 (identity). Follow-ons (own spec → plan): **1b** Apple Sign-in + sessions/scoped-token resolution wired into `current_player_id`; **1c** legacy-map resolution + threading `player_id` into the 7 IDOR call sites + `round_acl`/`access_audit` enforcement. This plan deliberately stops short of touching `server_v2/players_api.py` resolution or any route.

**Grounding (verified against code by the Phase-0 code map):**
- Auth seam today: `server_v2/players_api.py` (resolve) + gate middleware `server_v2/main.py:296`. Player store: `ai_caddie/rounds/players.py` — JSON registry `data/players/registry.json` (schema `ai-caddie-players-v1`), `OWNER_ID = "me"` (`players.py:14`), `p_*` ids, sha256 token hashes.
- App is a module singleton; the **only** async-startup seam is `_lifespan` at `server_v2/main.py:146` (today warms the stats cache).
- Data root: `ai_caddie/core/data.py` exposes `ROOT`.
- Deps are uv-managed (`pyproject.toml` `[project].dependencies` + `uv.lock`); CI runs `uv sync --frozen` then `uv run python -m unittest discover -s tests -v`, then boots the fixture API, then builds the Docker images and smoke-tests the API container with **no Postgres** present. **Therefore every test here must pass on SQLite, and the app must boot with the SQLite default.**
- `tests/` = ~97 flat `unittest` modules, no `conftest.py`, `TestClient(app)` instantiated per test. Mirror `tests/test_players_api_auth.py` (patches `players.ROOT` to a tmpdir).

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` / `uv.lock` | Modify: add `sqlalchemy`, `psycopg[binary]`, `alembic` to `[project].dependencies`; relock. |
| `server_v2/db.py` | Create: `AI_CADDIE_DATABASE_URL` resolution (SQLite default), lazy `Engine`, `session_scope()` context manager, `get_session` FastAPI dependency. |
| `server_v2/identity_models.py` | Create: SQLAlchemy `Base` + the 9 identity/tenancy tables. Portable types only. |
| `server_v2/identity_repo.py` | Create: pure functions over a `Session` — family/user/identity/legacy-map + session-token mint/resolve/revoke. No FastAPI, no globals. |
| `server_v2/identity_seed.py` | Create: idempotent backfill of the JSON player registry → `families`/`users`/`legacy_player_map`; runnable as `python -m server_v2.identity_seed`. |
| `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_identity.py` | Create: Alembic config + env (reads `AI_CADDIE_DATABASE_URL`, `target_metadata = Base.metadata`) + first migration creating the identity tables. |
| `server_v2/main.py:146` (`_lifespan`) | Modify: initialise the engine on startup (after the stats warm), tolerant of SQLite. |
| `ops/start_api.sh` | Modify: run `alembic upgrade head` before launching uvicorn (idempotent; creates tables on SQLite too). |
| `docker-compose.yml` | Modify: add a `db` (postgres) service + `AI_CADDIE_DATABASE_URL` on `api`; api `depends_on` db health. |
| `tests/test_deployment_manifests.py` | Modify: assert the new `db` service / `AI_CADDIE_DATABASE_URL` shape. |
| `tests/test_db_engine.py`, `tests/test_identity_models.py`, `tests/test_identity_migration.py`, `tests/test_identity_repo.py`, `tests/test_identity_seed.py`, `tests/test_app_boots_with_db.py` | Create: unit + integration tests (all on SQLite). |

**Conventions for portability (apply to every model/migration):** primary keys are `String(32)` holding `uuid.uuid4().hex`; timestamps are `DateTime` with **Python-side** defaults (`default=_utcnow`, never a DB `now()`); JSON via SQLAlchemy's generic `JSON` type (maps to `jsonb` on PG, `TEXT` on SQLite) — though Phase 1a needs none. No PG-only types in the identity tables.

---

## Task 1: Add database dependencies

**Files:**
- Modify: `pyproject.toml` (`[project].dependencies`)
- Modify: `uv.lock` (regenerated)
- Test: `tests/test_db_deps_importable.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_deps_importable.py
import unittest


class DatabaseDepsImportableTests(unittest.TestCase):
    def test_core_db_libraries_import(self):
        import alembic  # noqa: F401
        import sqlalchemy  # noqa: F401
        self.assertTrue(sqlalchemy.__version__.startswith("2."))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_db_deps_importable -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sqlalchemy'`.

- [ ] **Step 3: Add the dependencies and relock**

Run (updates `pyproject.toml` AND `uv.lock` together so `uv sync --frozen` stays green in CI/Docker):

```bash
uv add 'sqlalchemy>=2.0,<3' 'psycopg[binary]>=3.2' 'alembic>=1.13'
```

Confirm `pyproject.toml` `[project].dependencies` now lists the three, and `uv.lock` changed.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_db_deps_importable -v`
Expected: PASS.

- [ ] **Step 5: Verify the frozen install still resolves (CI parity)**

Run: `uv sync --frozen`
Expected: succeeds with no "lock drift" error.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/test_db_deps_importable.py
git commit -m "build(db): add sqlalchemy, psycopg, alembic for the identity layer"
```

---

## Task 2: Database engine + session module

**Files:**
- Create: `server_v2/db.py`
- Test: `tests/test_db_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_engine.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import text

from server_v2 import db


class DatabaseUrlTests(unittest.TestCase):
    def test_explicit_env_url_wins(self):
        with mock.patch.dict(os.environ, {"AI_CADDIE_DATABASE_URL": "sqlite:///x.db"}):
            self.assertEqual(db.database_url(), "sqlite:///x.db")

    def test_default_is_sqlite_under_root(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            url = db.database_url()
        self.assertTrue(url.startswith("sqlite:///"))
        self.assertTrue(url.endswith("identity.db"))

    def test_session_scope_executes_and_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'identity.db'}"
            with mock.patch.dict(os.environ, {"AI_CADDIE_DATABASE_URL": url}):
                db.reset_engine_for_tests()
                with db.session_scope() as session:
                    value = session.execute(text("select 1")).scalar_one()
                self.assertEqual(value, 1)
            db.reset_engine_for_tests()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_db_engine -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server_v2.db'`.

- [ ] **Step 3: Implement `server_v2/db.py`**

```python
# server_v2/db.py
"""SQLAlchemy engine/session for the identity layer.

Backend is chosen by ``AI_CADDIE_DATABASE_URL``: SQLite by default (dev/CI/
containers with no Postgres), PostgreSQL in docker-compose. Sync engine — the
existing routes are sync and run in FastAPI's threadpool.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_caddie.core.data import ROOT

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def database_url() -> str:
    explicit = os.environ.get("AI_CADDIE_DATABASE_URL")
    if explicit:
        return explicit
    return f"sqlite:///{Path(ROOT) / 'identity.db'}"


def get_engine() -> Engine:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _ENGINE = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
        _SESSION_FACTORY = sessionmaker(bind=_ENGINE, expire_on_commit=False, future=True)
    return _ENGINE


def _session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session: commit on success, rollback on error."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency form (1b/1c use it)."""
    with session_scope() as session:
        yield session


def reset_engine_for_tests() -> None:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_db_engine -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add server_v2/db.py tests/test_db_engine.py
git commit -m "feat(db): sqlite-default SQLAlchemy engine + session_scope"
```

---

## Task 3: Identity & tenancy models

**Files:**
- Create: `server_v2/identity_models.py`
- Test: `tests/test_identity_models.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_identity_models -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'server_v2.identity_models'`.

- [ ] **Step 3: Implement `server_v2/identity_models.py`**

```python
# server_v2/identity_models.py
"""Identity & tenancy tables (design §4). Portable across SQLite and Postgres."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, String, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Family(Base):
    __tablename__ = "families"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    owner_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    family_id: Mapped[str] = mapped_column(String(32), ForeignKey("families.id"))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="member")  # admin|member
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(32), default="apple")
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LegacyPlayerMap(Base):
    __tablename__ = "legacy_player_map"
    legacy_player_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 'me' | 'p_*'
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    install_uuid: Mapped[str] = mapped_column(String(64), unique=True)
    platform: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    device_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("devices.id"), nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="user")  # user|watch
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex of the bearer
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    refresh_of: Mapped[str | None] = mapped_column(String(32), nullable=True)


class TokenRevocation(Base):
    __tablename__ = "token_revocations"
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("sessions.id"), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AccessAudit(Base):
    __tablename__ = "access_audit"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    target_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_kind: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RoundAcl(Base):
    __tablename__ = "round_acl"
    round_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    access: Mapped[str] = mapped_column(String(32), default="owner")  # owner|shared_read
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_identity_models -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add server_v2/identity_models.py tests/test_identity_models.py
git commit -m "feat(db): identity & tenancy SQLAlchemy models (families/users/sessions/acl)"
```

---

## Task 4: Alembic setup + first migration

**Files:**
- Create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_identity.py`
- Test: `tests/test_identity_migration.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_identity_migration -v`
Expected: FAIL — no `alembic.ini` / `migrations`.

- [ ] **Step 3: Scaffold Alembic, then point env.py at our URL + metadata**

Run: `uv run alembic init migrations` (creates `alembic.ini` + `migrations/`). Then replace the generated `migrations/env.py` with:

```python
# migrations/env.py
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from server_v2.db import database_url
from server_v2.identity_models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Our app's URL wins over the static alembic.ini value (so SQLite/Postgres follow env).
config.set_main_option("sqlalchemy.url", config.get_main_option("sqlalchemy.url") or database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite-safe ALTERs for future migrations
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Autogenerate the first migration against an empty SQLite DB**

Run:

```bash
AI_CADDIE_DATABASE_URL="sqlite:///$(pwd)/.tmp_autogen.db" \
  uv run alembic -c alembic.ini revision --autogenerate -m "identity" --rev-id 0001_identity
rm -f .tmp_autogen.db
```

Open `migrations/versions/0001_identity.py` and verify `upgrade()` issues `op.create_table(...)` for all 9 tables (families, users, user_identities, legacy_player_map, devices, sessions, token_revocations, access_audit, round_acl) and the `uq_identity_provider_subject` constraint. Hand-fix only if autogen missed the unique constraint.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_identity_migration -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini migrations/ tests/test_identity_migration.py
git commit -m "feat(db): alembic + first migration creating identity tables (sqlite+pg)"
```

---

## Task 5: Repository — families/users/identities/legacy-map

**Files:**
- Create: `server_v2/identity_repo.py`
- Test: `tests/test_identity_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_identity_repo.py
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server_v2 import identity_repo as repo
from server_v2.identity_models import Base


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_identity_repo -v`
Expected: FAIL — no `server_v2.identity_repo`.

- [ ] **Step 3: Implement the family/user/map functions in `server_v2/identity_repo.py`**

```python
# server_v2/identity_repo.py
"""Repository functions over a SQLAlchemy Session. No FastAPI, no module globals."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from server_v2.identity_models import (
    Family, LegacyPlayerMap, User, UserIdentity,
)


def create_family_with_owner(session: Session, *, family_name: str, owner_display_name: str) -> tuple[Family, User]:
    family = Family(name=family_name)
    session.add(family)
    session.flush()  # assign family.id
    owner = User(family_id=family.id, display_name=owner_display_name, role="admin")
    session.add(owner)
    session.flush()
    family.owner_user_id = owner.id
    return family, owner


def add_user(session: Session, *, family_id: str, display_name: str, role: str = "member") -> User:
    user = User(family_id=family_id, display_name=display_name, role=role)
    session.add(user)
    session.flush()
    return user


def map_legacy_player(session: Session, *, legacy_player_id: str, user_id: str) -> LegacyPlayerMap:
    row = session.get(LegacyPlayerMap, legacy_player_id)
    if row is None:
        row = LegacyPlayerMap(legacy_player_id=legacy_player_id, user_id=user_id)
        session.add(row)
    else:
        row.user_id = user_id
    return row


def user_id_for_legacy_player(session: Session, legacy_player_id: str) -> str | None:
    row = session.get(LegacyPlayerMap, legacy_player_id)
    return row.user_id if row else None


def get_user_by_apple_subject(session: Session, subject: str) -> User | None:
    stmt = (
        select(User)
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(UserIdentity.provider == "apple", UserIdentity.subject == subject)
    )
    return session.execute(stmt).scalars().first()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_identity_repo -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add server_v2/identity_repo.py tests/test_identity_repo.py
git commit -m "feat(db): identity repo — family/owner/member + legacy-player map"
```

---

## Task 6: Repository — session token mint / resolve / revoke

**Files:**
- Modify: `server_v2/identity_repo.py`
- Test: `tests/test_identity_repo_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_identity_repo_sessions.py
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server_v2 import identity_repo as repo
from server_v2.identity_models import Base


class SessionTokenRepoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def _owner(self, s):
        _family, owner = repo.create_family_with_owner(s, family_name="F", owner_display_name="O")
        return owner

    def test_mint_returns_plaintext_once_and_resolves(self):
        with self.Session() as s:
            owner = self._owner(s)
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            token, sess = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=expires)
            s.commit()
            self.assertTrue(token)
            resolved = repo.resolve_session_token(s, token)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.user_id, owner.id)

    def test_expired_token_does_not_resolve(self):
        with self.Session() as s:
            owner = self._owner(s)
            past = datetime.now(timezone.utc) - timedelta(seconds=1)
            token, _ = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=past)
            s.commit()
            self.assertIsNone(repo.resolve_session_token(s, token))

    def test_revoked_token_does_not_resolve(self):
        with self.Session() as s:
            owner = self._owner(s)
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            token, sess = repo.mint_session_token(s, user_id=owner.id, scope="user", expires_at=future)
            repo.revoke_session(s, session_id=sess.id, reason="logout")
            s.commit()
            self.assertIsNone(repo.resolve_session_token(s, token))

    def test_unknown_token_returns_none(self):
        with self.Session() as s:
            self.assertIsNone(repo.resolve_session_token(s, "nope"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_identity_repo_sessions -v`
Expected: FAIL — `mint_session_token` does not exist.

- [ ] **Step 3: Add the session functions to `server_v2/identity_repo.py`**

Add these imports/helpers and functions (append; keep existing functions):

```python
# --- add to server_v2/identity_repo.py ---
import hashlib
import secrets
from datetime import datetime, timezone

from server_v2.identity_models import Session as SessionRow, TokenRevocation


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_session_token(
    session: Session, *, user_id: str, scope: str, expires_at: datetime,
    device_id: str | None = None, refresh_of: str | None = None,
) -> tuple[str, SessionRow]:
    """Create a session row; return (plaintext_token, row). Plaintext is shown ONCE."""
    token = secrets.token_urlsafe(32)
    row = SessionRow(
        user_id=user_id, device_id=device_id, scope=scope,
        token_hash=_hash_token(token), expires_at=expires_at, refresh_of=refresh_of,
    )
    session.add(row)
    session.flush()
    return token, row


def resolve_session_token(session: Session, token: str) -> SessionRow | None:
    """Return the live session for a bearer token, or None (unknown/expired/revoked)."""
    row = session.execute(
        select(SessionRow).where(SessionRow.token_hash == _hash_token(token))
    ).scalars().first()
    if row is None:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    if session.get(TokenRevocation, row.id) is not None:
        return None
    return row


def revoke_session(session: Session, *, session_id: str, reason: str | None = None) -> None:
    if session.get(TokenRevocation, session_id) is None:
        session.add(TokenRevocation(session_id=session_id, reason=reason))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_identity_repo_sessions -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add server_v2/identity_repo.py tests/test_identity_repo_sessions.py
git commit -m "feat(db): session token mint/resolve/revoke (hashed, expiry+revocation aware)"
```

---

## Task 7: Seed the legacy player registry into identity tables

**Files:**
- Create: `server_v2/identity_seed.py`
- Test: `tests/test_identity_seed.py`

- [ ] **Step 1: Write the failing test**

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_identity_seed -v`
Expected: FAIL — no `server_v2.identity_seed`.

- [ ] **Step 3: Implement `server_v2/identity_seed.py`**

```python
# server_v2/identity_seed.py
"""One-shot, idempotent backfill: JSON player registry -> families/users/legacy_player_map.

Phase 1a: identity rows only. No file data is moved (that is Phase 3 backfill).
Run as: python -m server_v2.identity_seed
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_caddie.rounds import players
from server_v2 import identity_repo as repo
from server_v2.db import session_scope
from server_v2.identity_models import Family, User

_FAMILY_NAME = "Family"


def seed_from_registry(session: Session, *, root: Path | None = None) -> dict[str, str]:
    """Create one family + a user per registry player + legacy map. Idempotent.

    Returns {legacy_player_id: user_id}.
    """
    registry = players.load_registry(root=root)
    rows = registry.get("players", [])
    owner_row = next((p for p in rows if p.get("isOwner")), {"id": players.OWNER_ID, "name": "我"})

    # Family + owner (only if the owner is not already mapped).
    owner_user_id = repo.user_id_for_legacy_player(session, owner_row["id"])
    if owner_user_id is None:
        existing_family = session.execute(select(Family)).scalars().first()
        if existing_family is None:
            family, owner = repo.create_family_with_owner(
                session, family_name=_FAMILY_NAME, owner_display_name=owner_row.get("name") or "我",
            )
        else:
            family = existing_family
            owner = repo.add_user(
                session, family_id=family.id,
                display_name=owner_row.get("name") or "我", role="admin",
            )
        repo.map_legacy_player(session, legacy_player_id=owner_row["id"], user_id=owner.id)
        owner_user_id = owner.id
    else:
        family = session.execute(select(Family)).scalars().first()

    result = {owner_row["id"]: owner_user_id}

    for p in rows:
        if p.get("isOwner"):
            continue
        legacy_id = p["id"]
        mapped = repo.user_id_for_legacy_player(session, legacy_id)
        if mapped is None:
            member = repo.add_user(
                session, family_id=family.id,
                display_name=p.get("name") or legacy_id, role="member",
            )
            repo.map_legacy_player(session, legacy_player_id=legacy_id, user_id=member.id)
            mapped = member.id
        result[legacy_id] = mapped

    return result


def main() -> None:
    with session_scope() as session:
        mapping = seed_from_registry(session)
    print(f"seeded {len(mapping)} legacy players -> users")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_identity_seed -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add server_v2/identity_seed.py tests/test_identity_seed.py
git commit -m "feat(db): idempotent seed of legacy me/p_* registry into identity tables"
```

---

## Task 8: Initialise the engine on app startup; migrate on boot

**Files:**
- Modify: `server_v2/main.py` (`_lifespan`, ~line 146)
- Modify: `ops/start_api.sh`
- Test: `tests/test_app_boots_with_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app_boots_with_db.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from server_v2 import db


class AppBootsWithDbTests(unittest.TestCase):
    def test_health_ok_and_identity_tables_exist_on_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite:///{Path(tmp) / 'identity.db'}"
            env = {
                "AI_CADDIE_DATABASE_URL": url,
                "AI_CADDIE_DATA_MODE": "fixture",
                "AI_CADDIE_SECURITY_PROFILE": "",
                "AI_CADDIE_ADMIN_TOKEN": "",
            }
            with mock.patch.dict(os.environ, env):
                db.reset_engine_for_tests()
                from server_v2.main import app  # imported under env
                with TestClient(app) as client:  # context = lifespan runs
                    self.assertEqual(client.get("/api/v2/health").status_code, 200)
                    from sqlalchemy import inspect
                    tables = set(inspect(db.get_engine()).get_table_names())
                    self.assertIn("users", tables)
            db.reset_engine_for_tests()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_app_boots_with_db -v`
Expected: FAIL — `users` table absent (lifespan does not create the schema yet).

- [ ] **Step 3: Initialise the schema in `_lifespan`**

In `server_v2/main.py`, add an import near the other `server_v2` imports:

```python
from server_v2 import db as _db
from server_v2.identity_models import Base as _IdentityBase
```

Then extend `_lifespan` (currently at `main.py:146`, body warms the stats cache) to create the identity schema. Use `create_all` here — it is idempotent and SQLite/Postgres-safe; the authoritative migration path for Postgres deploys is `alembic upgrade head` in `start_api.sh` (Step 4), and `create_all` no-ops when the tables already exist:

```python
@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    warm_stats_cache_in_background()
    try:
        _IdentityBase.metadata.create_all(_db.get_engine())
    except Exception:  # never block API boot on identity-store init (Phase 1a is additive)
        logger.exception("identity schema init failed")
    yield
```

(If `main.py` has no module `logger`, use `logging.getLogger(__name__)` — check the top of the file and reuse whatever is there.)

- [ ] **Step 4: Run `alembic upgrade head` before launching uvicorn**

In `ops/start_api.sh`, **before** the `exec uvicorn ...` / uvicorn launch line, add (matching the script's existing style and the way it already invokes Python):

```sh
# Bring the identity DB schema up to date (Postgres in prod; the SQLite default
# is created here too). Idempotent; fail-closed so a broken migration stops boot.
alembic upgrade head
```

If the script runs commands via `uv run`, prefix accordingly (`uv run alembic upgrade head`); match the existing invocations in the file.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_app_boots_with_db -v`
Expected: PASS.

- [ ] **Step 6: Full-suite regression (the lifespan now touches the DB on every boot)**

Run: `uv run python -m unittest discover -s tests -v`
Expected: PASS (no existing test regressed; the fixture app still boots).

- [ ] **Step 7: Commit**

```bash
git add server_v2/main.py ops/start_api.sh tests/test_app_boots_with_db.py
git commit -m "feat(db): create identity schema on lifespan; alembic upgrade on api start"
```

---

## Task 9: Add the Postgres service to docker-compose

**Files:**
- Modify: `docker-compose.yml`
- Modify: `tests/test_deployment_manifests.py`

- [ ] **Step 1: Read the current manifest test to learn its assertion style**

Run: `uv run python -m unittest tests.test_deployment_manifests -v` (confirm green now), and open `tests/test_deployment_manifests.py` to see how it parses `docker-compose.yml` (it asserts env-var/secret shape).

- [ ] **Step 2: Write the failing test (extend the manifest test)**

Add to `tests/test_deployment_manifests.py` a test asserting the new service + wiring (adapt the YAML-loading helper already in the file):

```python
def test_compose_has_postgres_and_api_database_url(self):
    compose = self._load_compose()  # reuse the file's existing loader
    services = compose["services"]
    self.assertIn("db", services)
    self.assertIn("postgres", services["db"]["image"])
    api_env = services["api"].get("environment", {})
    # environment may be a list or a dict depending on the file's style; normalize:
    keys = api_env.keys() if isinstance(api_env, dict) else {e.split("=", 1)[0] for e in api_env}
    self.assertIn("AI_CADDIE_DATABASE_URL", keys)
    self.assertIn("db", services["api"].get("depends_on", {}))
```

(If the file has no `_load_compose`, add a small `yaml.safe_load` helper mirroring how it loads other manifests.)

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_deployment_manifests -v`
Expected: FAIL — no `db` service.

- [ ] **Step 4: Add the `db` service + wire the api**

In `docker-compose.yml` add a `db` service and extend `api`:

```yaml
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: aicaddie
      POSTGRES_PASSWORD: ${AI_CADDIE_DB_PASSWORD:-aicaddie}
      POSTGRES_DB: aicaddie
    volumes:
      - ai-caddie-pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aicaddie"]
      interval: 5s
      timeout: 3s
      retries: 20
```

On the existing `api` service, add to `environment:`:

```yaml
      AI_CADDIE_DATABASE_URL: postgresql+psycopg://aicaddie:${AI_CADDIE_DB_PASSWORD:-aicaddie}@db:5432/aicaddie
```

and add:

```yaml
    depends_on:
      db:
        condition: service_healthy
```

Add `ai-caddie-pgdata:` under the top-level `volumes:` block.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_deployment_manifests -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml tests/test_deployment_manifests.py
git commit -m "feat(db): add postgres service + AI_CADDIE_DATABASE_URL wiring to compose"
```

---

## Task 10: Phase-1a green gate (full suite + boot parity)

**Files:** none (verification only)

- [ ] **Step 1: Run the entire backend suite the way CI does**

Run: `uv run python -m unittest discover -s tests -v`
Expected: all PASS, including the 7 new test modules.

- [ ] **Step 2: Compile-check every source (CI parity)**

Run: `uv run python -m py_compile $(git ls-files '*.py')`
Expected: exit 0.

- [ ] **Step 3: Frozen-lock check (CI parity)**

Run: `uv sync --frozen`
Expected: no drift error.

- [ ] **Step 4: Boot the fixture API and confirm health (CI parity)**

Run:
```bash
AI_CADDIE_DATA_MODE=fixture AI_CADDIE_SECURITY_PROFILE=private AI_CADDIE_ADMIN_TOKEN=ci-admin-token \
  uv run uvicorn server_v2.main:app --host 127.0.0.1 --port 9000 & echo $! > /tmp/p1a.pid
sleep 3 && curl -fsS http://127.0.0.1:9000/api/v2/health && kill "$(cat /tmp/p1a.pid)"
```
Expected: `{"status":"ok"...}`-shaped 200 (the SQLite identity store created silently under the data root).

- [ ] **Step 5: Exercise the seeder end-to-end on a throwaway SQLite DB**

Run:
```bash
AI_CADDIE_DATABASE_URL="sqlite:///$(pwd)/.tmp_seed.db" uv run alembic upgrade head
AI_CADDIE_DATABASE_URL="sqlite:///$(pwd)/.tmp_seed.db" uv run python -m server_v2.identity_seed
rm -f .tmp_seed.db
```
Expected: prints `seeded N legacy players -> users` with no error.

- [ ] **Step 6: Open the PR**

```bash
git push -u origin superpowers/phase1a-db-identity-foundation
gh pr create --base integration/v2 --title "Phase 1a: DB foundation + identity schema" \
  --body "Stands up Postgres (SQLite default) + SQLAlchemy identity/tenancy schema + repo layer + legacy me/p_* seeder. Purely additive — no route or auth-resolution change (that is 1b/1c). All tests on SQLite; fixture API + Docker smoke stay green with the SQLite default.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Confirm CI (backend + docker) is green before merge. **Do not** pass `--delete-branch` on merge.

---

## Self-Review

**Spec coverage (design §4 identity block + §10 phase 1 + §8.1):**
- ✅ All 9 identity/tenancy tables (`families/users/user_identities/legacy_player_map/devices/sessions/token_revocations/access_audit/round_acl`) — Task 3.
- ✅ "Stand up the DB" (§8.1) — Tasks 2/4/8/9.
- ✅ Legacy `me`/`p_*` migration of identity rows (§5, §10.1) — Task 7.
- ✅ Session token primitive for 1b's scoped tokens (§5) — Task 6 (mint/resolve/revoke, hashed, expiry+revocation).
- ⏭ Deferred to 1b/1c by design: Apple sign-in HTTP, `current_player_id` resolution change, IDOR `player_id` threading, ACL/audit *enforcement*, watch-token issuance. The tables/repo they need exist after 1a.

**Placeholder scan:** none — every code step is complete and runnable.

**Type/name consistency:** `Session` ORM class is imported `as SessionRow` in the repo (Task 6) to avoid colliding with SQLAlchemy's `Session`; `mint_session_token`/`resolve_session_token`/`revoke_session` names match between Task 6 impl and its test; `user_id_for_legacy_player`/`map_legacy_player`/`create_family_with_owner`/`add_user` names match between Tasks 5/7 and their tests; `db.reset_engine_for_tests`/`db.get_engine`/`db.session_scope`/`db.database_url` match across Tasks 2/8/10.

**Portability check:** identity tables use only `String/DateTime/Boolean/ForeignKey/UniqueConstraint`; timestamps default Python-side (`_utcnow`); `resolve_session_token` normalises SQLite's naive datetimes to UTC before comparison — so every test passes on SQLite and the same migration applies to Postgres.

**Risk check:** Phase 1a adds no read of the DB to any existing route; the only runtime change to existing behavior is `_lifespan` calling `create_all` (wrapped in try/except so a DB hiccup can't block API boot) and `start_api.sh` running `alembic upgrade head`. Both are exercised by Task 8 + Task 10's boot steps.
