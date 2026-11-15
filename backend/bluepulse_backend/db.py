from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    default = Path(__file__).resolve().parents[1] / "data" / "bluepulse.db"
    return os.environ.get("BLUEPULSE_DATABASE_URL", f"sqlite:///{default.as_posix()}")


def make_engine(url: str | None = None, *, request_scoped: bool = False) -> Engine:
    address = url or database_url()
    ensure_sqlite_parent(address)
    options = {"connect_args": {"timeout": 30}} if address.startswith("sqlite:") else {}
    if request_scoped and address.startswith("sqlite:///") and ":memory:" not in address:
        # An unfinished SELECT can pin a SQLite WAL snapshot past pool rollback.
        options["poolclass"] = NullPool
    return create_engine(address, pool_pre_ping=True, **options)


def ensure_sqlite_parent(address: str) -> None:
    if address.startswith("sqlite:///") and address != "sqlite:///:memory:":
        Path(address.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
