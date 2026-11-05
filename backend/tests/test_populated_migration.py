from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import make_engine
from bluepulse_backend.material_identity import title_key
from bluepulse_backend.models import Material


def test_populated_pre_attachment_db_upgrades_and_reconciles_identity(tmp_path, monkeypatch):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "old-populated.db"
    url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", url)
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    command.upgrade(config, "b2f7e61c904a")

    with sqlite3.connect(database) as conn:
        for index, allowed in ((1, 1), (2, 0)):
            source_id = f"00000000-0000-0000-0000-{index:012d}"
            conn.execute("""INSERT INTO sources
                (id,slug,name,region,language,source_type,topics,allowed_hosts,
                 enabled,excerpt_allowed,full_text_allowed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id, f"source-{index}", f"Source {index}", "foreign", "en",
                 "official", "[]", '["www.nist.gov"]', 1, allowed, 0))
            conn.execute("""INSERT INTO materials
                (id,canonical_url,source_url,source_id,source_title,source_body,language,
                 published_at,first_seen_at,fetched_at,revision,content_hash,state,
                 timeline_kind,body_status,translation_status,importance_score,topics,
                 featured_candidate,grouping_status,public,withdrawn,title_key)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"10000000-0000-0000-0000-{index:012d}",
                 f"https://www.nist.gov/news-events/news/copy-{index}",
                 f"https://www.nist.gov/news-events/news/copy-{index}", source_id,
                 "Police radio interoperability study", "Police radio evidence. " * 30,
                 "en", "2026-11-03 00:00:00.000000", "2026-11-03 02:00:00.000000",
                 "2026-11-03 02:00:00.000000", 1, "a" * 64, "analysis_pending",
                 "fresh", "full_text", "pending", 0, "[]", 0, "pending", 0, 0,
                 title_key("Police radio interoperability study")))
    command.upgrade(config, "head")
    engine = make_engine(url)
    with Session(engine) as session:
        rows = session.scalars(select(Material).order_by(Material.id)).all()
        assert len(rows) == 2
        assert rows[0].duplicate_of_id is None
        assert rows[1].duplicate_of_id == rows[0].id
        assert rows[1].state == "duplicate_hidden"
        assert all(row.selection_status == "pending" for row in rows)
    engine.dispose()
