from __future__ import annotations

import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bluepulse_backend.api import create_app, get_session
from bluepulse_backend.models import Article, Base, Source


class RecentlyCollectedTests(unittest.TestCase):
    def test_fallback_uses_collection_order_but_preserves_original_publication_date(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as session, session.begin():
            source = Source(slug="test-source", name="Test Source", base_url="https://example.org", adapter="rss")
            session.add(source)
            session.flush()
            items = (
                ("older-published", datetime(2026, 10, 2, tzinfo=UTC),
                 datetime(2021, 4, 1, tzinfo=UTC), "processed", "summary_only", None),
                ("newer-published", datetime(2026, 10, 1, tzinfo=UTC),
                 datetime(2026, 9, 30, tzinfo=UTC), "processed", "summary_only", None),
                ("withheld", datetime(2026, 10, 3, tzinfo=UTC),
                 datetime(2026, 10, 3, tzinfo=UTC), "processed", "summary_only", "irrelevant"),
                ("title-only", datetime(2026, 10, 4, tzinfo=UTC),
                 None, "pending_model", "metadata_only", None),
            )
            for slug, seen, published, status, parse_status, editorial in items:
                session.add(Article(
                    source_id=source.id, source_url=f"https://example.org/{slug}",
                    canonical_url=f"https://example.org/{slug}", source_title=slug,
                    first_seen_at=seen, published_at=published,
                    processing_status=status, parse_status=parse_status,
                    editorial_relevance=editorial, zh_summary=f"{slug} summary",
                ))

        def session_override():
            with Session(engine) as session:
                yield session

        app = create_app()
        app.dependency_overrides[get_session] = session_override
        with TestClient(app) as client:
            response = client.get("/api/v1/home/recently-collected")
            self.assertEqual(response.status_code, 200)
            articles = response.json()["items"]
            self.assertEqual([item["source_title"] for item in articles],
                             ["older-published", "newer-published"])
            self.assertEqual(articles[0]["first_seen_at"], "2026-10-02T00:00:00Z")
            self.assertEqual(articles[0]["published_at"], "2021-04-01T00:00:00Z")
            self.assertEqual(articles[0]["summary"], "older-published summary")
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
