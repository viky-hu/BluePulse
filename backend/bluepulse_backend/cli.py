from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.engine import make_url

from .db import database_url, make_engine, make_session_factory
from .models import Topic
from .pipeline import LEGACY_TOPIC_SLUGS
from .source_collection import SOURCES, ensure_source
from .work_queue import serialized


TOPICS = (
    ("product", "产品", "Product"),
    ("practice", "实战", "Practice"),
    ("paper", "论文", "Paper"),
    ("law", "法制", "Law"),
    ("embodied", "具身", "Embodied"),
    ("public-opinion", "舆情", "Public Opinion"),
    ("low-altitude", "低空", "Low Altitude"),
)


def migration_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    return config


def migrate() -> None:
    command.upgrade(migration_config(), "head")


def sync_taxonomy(database_url: str | None = None) -> None:
    engine = make_engine(database_url)
    try:
        factory = make_session_factory(engine)
        with factory() as session:
            for slug, zh, en in TOPICS:
                topic = session.scalar(select(Topic).where(Topic.slug == slug))
                if topic is None:
                    session.add(Topic(slug=slug, name_zh=zh, name_en=en))
                else:
                    topic.name_zh, topic.name_en, topic.enabled = zh, en, True
            # Preserve legacy classifications for exact old links, but keep them out
            # of the seven current frontend category choices.
            for topic in session.scalars(select(Topic).where(Topic.slug.in_(sorted(LEGACY_TOPIC_SLUGS)))):
                topic.enabled = False
            session.commit()
    finally:
        engine.dispose()


def sync_sources() -> None:
    engine = make_engine()
    try:
        with serialized(engine) as session:
            for spec in SOURCES.values():
                ensure_source(session, spec, commit=False)
    finally:
        engine.dispose()


def _backup_before_upgrade(config: Config):
    url = make_url(database_url())
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return
    path = Path(url.database).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        return
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source:
        table = source.execute("SELECT 1 FROM sqlite_master WHERE name = 'alembic_version'").fetchone()
        versions = {row[0] for row in source.execute("SELECT version_num FROM alembic_version")} if table else set()
        if versions == set(ScriptDirectory.from_config(config).get_heads()):
            return
        backups = path.parent / "backups"
        backups.mkdir(exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = backups / f"{path.stem}-{timestamp}.sqlite3"
        with sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("migration_backup_integrity_failed")


def initialize() -> None:
    config = migration_config()
    _backup_before_upgrade(config)
    command.upgrade(config, "head")
    sync_taxonomy()
    sync_sources()


def main() -> None:
    parser = argparse.ArgumentParser(description="Blue Pulse backend local setup")
    parser.add_argument("command", choices=["migrate", "sync-taxonomy", "sync-sources", "initialize"])
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "sync-taxonomy":
        sync_taxonomy()
    elif args.command == "sync-sources":
        sync_sources()
    else:
        initialize()


if __name__ == "__main__":
    main()
