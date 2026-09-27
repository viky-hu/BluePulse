from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_ROOT / 'data' / 'bluepulse-dev.db').as_posix()}"


def get_database_url() -> str:
    database_url = os.environ.get("BLUEPULSE_DATABASE_URL", "").strip()
    if database_url:
        return database_url
    (BACKEND_ROOT / "data").mkdir(parents=True, exist_ok=True)
    return DEFAULT_DATABASE_URL


def create_database_engine() -> Engine:
    database_url = get_database_url()
    if database_url.startswith("sqlite:"):
        (BACKEND_ROOT / "data").mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    if not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "BLUEPULSE_DATABASE_URL must use sqlite:/// or postgresql+psycopg://."
        )
    return create_engine(database_url, pool_pre_ping=True)
