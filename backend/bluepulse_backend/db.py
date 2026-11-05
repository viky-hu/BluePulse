from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    default = Path(__file__).resolve().parents[1] / "data" / "bluepulse.db"
    return os.environ.get("BLUEPULSE_DATABASE_URL", f"sqlite:///{default.as_posix()}")


def make_engine(url: str | None = None) -> Engine:
    address = url or database_url()
    ensure_sqlite_parent(address)
    return create_engine(address, pool_pre_ping=True)


def ensure_sqlite_parent(address: str) -> None:
    if address.startswith("sqlite:///") and address != "sqlite:///:memory:":
        Path(address.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
