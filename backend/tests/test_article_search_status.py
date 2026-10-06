"""Migration-backed search and public content-state contract checks."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app, get_session
from bluepulse_backend.models import Article, Source


class ArticleSearchStatusTests(unittest.TestCase):
    def test_migration_indexes_existing_and_updated_chinese_body(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_url = f"sqlite:///{(Path(temporary) / 'search.db').as_posix()}"
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            with patch.dict(os.environ, {"BLUEPULSE_DATABASE_URL": database_url}):
                command.upgrade(config, "0006_ingestion_lease")
                engine = create_engine(database_url)
                with Session(engine) as session, session.begin():
                    source = Source(slug="test-source", name="Test", adapter="rss",
                                    base_url="https://example.org", enabled=True)
                    session.add(source)
                    session.flush()
                    source_id = source.id
                    article_id = uuid4()
                    session.execute(text("""
                        INSERT INTO articles (id, source_id, source_url, canonical_url,
                            source_title, source_body, zh_body, zh_summary, language,
                            parse_status, processing_status, published_at, first_seen_at, fetched_at,
                            importance_score, featured_candidate, quality_status)
                        VALUES (:id, :source_id, :url, :url, :title, :body, :zh_body, :summary,
                            'en', 'full_text', 'processed', :now, :now, :now, 0, 0, 'unreviewed')
                    """), {"id": article_id.hex, "source_id": source.id.hex,
                           "url": "https://example.org/one", "title": "技术测试文章",
                           "body": "This is an English report.", "zh_body": "采用无人机开展警务巡查。",
                           "summary": "报道介绍技术试点。", "now": datetime.now(UTC)})
                command.upgrade(config, "head")
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT count(*) FROM article_search")).scalar(), 1)

            def session_override():
                with Session(engine) as session:
                    yield session

            app = create_app()
            app.dependency_overrides[get_session] = session_override
            try:
                with TestClient(app) as client:
                    search = client.get("/api/v1/articles", params={"period": "all", "q": "无人机"})
                    self.assertEqual(search.status_code, 200)
                    self.assertEqual(len(search.json()["items"]), 1)
                    self.assertEqual(search.json()["items"][0]["translation_status"], "available")
                    self.assertEqual(len(client.get("/api/v1/articles", params={"period": "all", "q": "无人"}).json()["items"]), 1)
                    with Session(engine) as session, session.begin():
                        article = session.get(Article, article_id)
                        article.zh_body = "使用警务智能体辅助巡查。"
                        article.translation_status = "available"
                    self.assertEqual(client.get("/api/v1/articles", params={"period": "all", "q": "无人机"}).json()["items"], [])
                    self.assertEqual(len(client.get("/api/v1/articles", params={"period": "all", "q": "智能体"}).json()["items"]), 1)
                    detail = client.get(f"/api/v1/articles/{article_id}").json()
                    self.assertEqual(detail["body_status"], "full_text")
                    self.assertEqual(detail["translation_status"], "available")
                    with Session(engine) as session, session.begin():
                        added = Article(source_id=source_id, source_url="https://example.org/two",
                                        canonical_url="https://example.org/two", source_title="新试点",
                                        source_body="新型警务机器人参与巡查。", language="zh",
                                        parse_status="full_text", processing_status="processed",
                                        published_at=datetime.now(UTC))
                        session.add(added)
                        session.flush()
                        added_id = added.id
                    self.assertEqual(len(client.get("/api/v1/articles", params={"period": "all", "q": "机器人"}).json()["items"]), 1)
                    with Session(engine) as session, session.begin():
                        session.delete(session.get(Article, added_id))
                    self.assertEqual(client.get("/api/v1/articles", params={"period": "all", "q": "机器人"}).json()["items"], [])
            finally:
                engine.dispose()

    def test_missing_body_and_failed_translation_are_distinct(self) -> None:
        article = Article(source_title="Example", source_body="English full text",
                          language="en", parse_status="full_text", translation_status="failed")
        from bluepulse_backend.api import _content_status
        self.assertEqual(_content_status(article), ("full_text", "failed"))
        article.source_body = None
        article.zh_summary = "只有摘要"
        self.assertEqual(_content_status(article), ("summary_only", "failed"))
        article.translation_status = None
        self.assertEqual(_content_status(article), ("summary_only", "source_unavailable"))


if __name__ == "__main__":
    unittest.main()
