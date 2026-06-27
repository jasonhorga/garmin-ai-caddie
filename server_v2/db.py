# server_v2/db.py
"""SQLAlchemy engine/session for the identity layer.

Backend is chosen by ``AI_CADDIE_DATABASE_URL``: SQLite by default (dev/CI/
containers with no Postgres), PostgreSQL in docker-compose. Sync engine — the
existing routes are sync and run in FastAPI's threadpool.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ai_caddie.core.data import ROOT

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite leaves FK enforcement OFF by default; enable it on every sqlite connection
    so dev/CI/test (SQLite) match production (Postgres). No-op on non-sqlite connections."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def database_url() -> str:
    explicit = os.environ.get("AI_CADDIE_DATABASE_URL")
    if explicit:
        return explicit
    return f"sqlite:///{Path(ROOT) / 'data' / 'identity.db'}"  # under the gitignored data/ dir


def ensure_sqlite_parent(url: str) -> None:
    """For a file-based sqlite URL, create the parent directory if it is missing.

    Used by both ``get_engine`` and Alembic's ``env.py`` (which builds its own engine),
    so a fresh deploy can open ``sqlite:///<root>/data/identity.db`` before the dir exists.
    """
    if not url.startswith("sqlite:///"):
        return
    db_file = url[len("sqlite:///"):]
    if db_file and db_file != ":memory:":
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        ensure_sqlite_parent(url)
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
