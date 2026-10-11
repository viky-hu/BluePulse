from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bluepulse_backend.api import create_app, get_session
from bluepulse_backend.models import Article, Base, Source


class ArticleAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.ids = {}
        with Session(self.engine) as session, session.begin():
            source = Source(slug="test", name="Test", base_url="https://example.org", adapter="rss")
            session.add(source)
            session.flush()
            variants = {
                "public": {},
                "potential": {"editorial_relevance": "potential"},
                "deleted": {"deleted_at": datetime.now(UTC)},
                "pending": {"processing_status": "pending_model"},
                "blocked": {"processing_status": "blocked"},
                "metadata": {"parse_status": "metadata_only"},
                "irrelevant": {"editorial_relevance": "irrelevant"},
                "uncertain": {"editorial_select": "uncertain"},
            }
            for name, overrides in variants.items():
                values = dict(source_id=source.id, source_url=f"https://example.org/{name}",
                              canonical_url=f"https://example.org/{name}", source_title=name,
                              processing_status="processed", parse_status="summary_only")
                values.update(overrides)
                article = Article(**values)
                session.add(article)
                session.flush()
                self.ids[name] = str(article.id)

        def session_override():
            with Session(self.engine) as session:
                yield session

        app = create_app()
        app.dependency_overrides[get_session] = session_override
        self.client = TestClient(app)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.client.close)

    def test_anonymous_batch_matches_public_detail_policy_without_internal_fields(self) -> None:
        unknown = str(uuid4())
        ids = [*self.ids.values(), unknown]
        response = self.client.get("/api/v1/articles/availability", params={"ids": ",".join(ids)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"items": [
            {"id": article_id, "available": article_id in (self.ids["public"], self.ids["potential"])}
            for article_id in ids
        ]})
        for item in response.json()["items"]:
            detail = self.client.get(f'/api/v1/articles/{item["id"]}')
            self.assertEqual(detail.status_code, 200 if item["available"] else 404)

    def test_canonicalizes_duplicates_in_first_input_order_with_one_id_only_select(self) -> None:
        statements = []
        def capture(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", capture)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", capture)
        ids = [self.ids["deleted"], self.ids["public"].upper(), self.ids["deleted"], self.ids["public"]]
        response = self.client.get("/api/v1/articles/availability", params={"ids": ",".join(ids)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [
            {"id": self.ids["deleted"], "available": False},
            {"id": self.ids["public"], "available": True},
        ]})
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0].startswith("SELECT articles.id "))

    def test_empty_input_returns_empty_items(self) -> None:
        response = self.client.get("/api/v1/articles/availability", params={"ids": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_invalid_or_more_than_100_input_ids_use_existing_validation_envelope(self) -> None:
        for ids in ("invalid", self.ids["public"] + ",", ",".join([self.ids["public"]] * 101)):
            with self.subTest(ids=ids):
                response = self.client.get("/api/v1/articles/availability", params={"ids": ids})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.headers.get("cache-control"), "no-store")
                self.assertEqual(response.json()["error"]["code"], "invalid_request")
                self.assertEqual(response.json()["error"]["request_id"], response.headers["x-request-id"])

    def test_accepts_100_input_ids(self) -> None:
        response = self.client.get("/api/v1/articles/availability",
                                   params={"ids": ",".join([self.ids["public"]] * 100)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": [{"id": self.ids["public"], "available": True}]})


if __name__ == "__main__":
    unittest.main()
