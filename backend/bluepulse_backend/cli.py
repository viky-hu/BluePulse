from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from .db import make_engine, make_session_factory
from .models import Topic
from .pipeline import LEGACY_TOPIC_SLUGS


TOPICS = (
    ("product", "产品", "Product"),
    ("practice", "实战", "Practice"),
    ("paper", "论文", "Paper"),
    ("law", "法制", "Law"),
    ("embodied", "具身", "Embodied"),
    ("public-opinion", "舆情", "Public Opinion"),
    ("low-altitude", "低空", "Low Altitude"),
)


def migrate() -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Blue Pulse backend local setup")
    parser.add_argument("command", choices=["migrate", "sync-taxonomy"])
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    else:
        sync_taxonomy()


if __name__ == "__main__":
    main()
