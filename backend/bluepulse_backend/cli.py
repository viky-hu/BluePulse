from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

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
    ("other", "其它", "Other"),
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
            # of the current frontend category choices.
            for topic in session.scalars(select(Topic).where(Topic.slug.in_(sorted(LEGACY_TOPIC_SLUGS)))):
                topic.enabled = False
            session.commit()
    finally:
        engine.dispose()


def sync_sources(*, local_live: bool = False) -> None:
    engine = make_engine()
    try:
        with serialized(engine) as session:
            sources = [ensure_source(session, spec, commit=False) for spec in SOURCES.values()]
            if local_live:
                from .source_permissions import initialize_local_live
                initialize_local_live(session, sources)
    finally:
        engine.dispose()


def _database_file() -> Path | None:
    url = make_url(database_url())
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database).resolve()
    return path if path.is_file() and path.stat().st_size else None


def _save_backup(source: sqlite3.Connection, path: Path) -> Path:
    backups = path.parent / "backups"
    backups.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backups / f"{path.stem}-{timestamp}.sqlite3"
    temporary = destination.with_suffix(".partial")
    try:
        with closing(sqlite3.connect(temporary)) as target:
            source.backup(target)
            if target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("database_backup_integrity_failed")
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def backup() -> Path:
    path = _database_file()
    if path is None:
        raise RuntimeError("backup_requires_existing_sqlite_database")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
        return _save_backup(source, path)


def _backup_before_upgrade(config: Config):
    path = _database_file()
    if path is None:
        return
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
        table = source.execute("SELECT 1 FROM sqlite_master WHERE name = 'alembic_version'").fetchone()
        versions = {row[0] for row in source.execute("SELECT version_num FROM alembic_version")} if table else set()
        if versions == set(ScriptDirectory.from_config(config).get_heads()):
            return
        _save_backup(source, path)


def initialize(*, local_live: bool = False) -> None:
    config = migration_config()
    _backup_before_upgrade(config)
    command.upgrade(config, "head")
    if local_live and (path := _database_file()) is not None:
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=30)) as connection:
            # Public reads can overlap worker commits during collection and publishing.
            if connection.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
                raise RuntimeError("local_database_wal_unavailable")
    sync_taxonomy()
    sync_sources(local_live=local_live)


def daily_range(start: date, end: date, *, execute: bool, reason: str | None):
    from .admin_security import audit
    from .daily_reports import compose_daily, daily_window, prepare_daily
    from .edition_models import DailyIssue

    now = datetime.now(UTC)
    if start > end or daily_window(end.isoformat())[1] > now:
        raise ValueError("daily_range_not_due")
    if execute and not (reason or "").strip():
        raise ValueError("daily_correction_requires_reason")
    path = _database_file()
    if path is None:
        raise ValueError("daily_requires_existing_sqlite_database")
    engine = make_engine() if execute else create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30))
    try:
        for offset in range((end - start).days + 1):
            key = (start + timedelta(days=offset)).isoformat()
            if not execute:
                with Session(engine) as session:
                    content, candidates = prepare_daily(session, key, now)
                print(json.dumps({"key": key, "main": len(content["main"]), "flashes": len(content["flashes"]),
                                  **content["generator"], "candidates": candidates}, ensure_ascii=False))
                continue
            with serialized(engine) as session:
                issue = session.get(DailyIssue, key)
                previous = issue.version if issue else None
                result = compose_daily(session, key, now=now, reason=reason, actor="maintenance",
                                       expected_version=previous, commit=False)
                if result["written"]:
                    audit(session, "daily.correct" if issue else "daily.recover", f"daily:{key}", reason=reason,
                          changes={"before": previous, "after": result["version"]})
            print(json.dumps(result, ensure_ascii=False))
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Blue Pulse backend local setup")
    parser.add_argument("command", choices=["migrate", "sync-taxonomy", "sync-sources", "initialize", "backup", "daily-range"])
    parser.add_argument("--local-live", action="store_true", help="apply the approved local publication defaults")
    parser.add_argument("--from-date", type=date.fromisoformat)
    parser.add_argument("--through-date", type=date.fromisoformat)
    parser.add_argument("--execute", action="store_true", help="write or revise daily editions")
    parser.add_argument("--reason", help="audit reason for a daily maintenance run")
    args = parser.parse_args()
    if args.local_live and args.command != "initialize":
        parser.error("--local-live requires initialize")
    if args.command == "daily-range":
        if args.from_date is None or args.through_date is None:
            parser.error("daily-range requires --from-date and --through-date")
        try:
            daily_range(args.from_date, args.through_date, execute=args.execute, reason=args.reason)
        except ValueError as exc:
            parser.error(str(exc))
        return
    if any((args.from_date, args.through_date, args.execute, args.reason)):
        parser.error("daily range options require daily-range")
    if args.command == "migrate":
        migrate()
    elif args.command == "sync-taxonomy":
        sync_taxonomy()
    elif args.command == "sync-sources":
        sync_sources()
    elif args.command == "backup":
        print(backup())
    else:
        initialize(local_live=args.local_live)


if __name__ == "__main__":
    main()
