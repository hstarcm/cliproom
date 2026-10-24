"""SQLite engine and session factory (WAL mode per SPECS.md §5)."""

from __future__ import annotations

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

_engine = None
_SessionLocal = None


def init_engine(db_path: str):
    """Create the engine for the given SQLite path (idempotent per path)."""
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine, _SessionLocal
    directory = os.path.dirname(db_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine, _SessionLocal


def get_engine():
    if _engine is None:
        raise RuntimeError("engine not initialised — call init_engine() first")
    return _engine


def session_factory():
    if _SessionLocal is None:
        raise RuntimeError("engine not initialised — call init_engine() first")
    return _SessionLocal
