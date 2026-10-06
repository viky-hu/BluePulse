from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app, get_session
from bluepulse_backend.ingestion.adapters import FetchedArticle
from bluepulse_backend.ingestion.entities import match_entities
from bluepulse_backend.ingestion.pipeline import _article_from_item, backfill_entities, sync_reference_data
from bluepulse_backend.models import Article, ArticleEntity, Base, Entity, Source


class EntityTests(unittest.TestCase):
    def test_alias_boundary_and_evidence(self) -> None:
        entity = Entity(slug="axon", entity_type="vendor", name="Axon",
                        aliases=["Axon Enterprise"], enabled=True)
        article = Article(source_title="A taxonomic police study", source_body="Taxon cameras are discussed.")
        self.assertEqual(match_entities(article, [entity]), [])
        article.source_body = "Police selected Axon Enterprise for a pilot."
        self.assertEqual([(field, alias) for _, field, alias in match_entities(article, [entity])],
                         [("source_body", "Axon Enterprise")])

    def test_catalog_backfill_api_filter_and_soft_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{(Path(temp_dir) / 'test.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                       side_effect=lambda: create_engine(database_url)):
                synced = sync_reference_data()
                self.assertEqual(synced["entities"], 10)
                with Session(engine) as session, session.begin():
                    source = session.scalar(select(Source).where(Source.slug == "gdelt-public-news"))
                    now = datetime.now(UTC)
                    for slug, body, status in (
                        ("axon", "Police selected Axon Enterprise for a camera pilot.", "processed"),
                        ("axon-2", "A second Axon Enterprise camera report.", "processed"),
                        ("chatgpt", "Police used ChatGPT to draft text.", "processed"),
                        ("irrelevant", "Axon Enterprise made a product.", "irrelevant"),
                    ):
                        article = _article_from_item(FetchedArticle(
                            url=f"https://example.org/{slug}", title="Police technology report",
                            body=body, published_at=now, language="en", parse_status="full_text",
                            processing_status=status,
                        ), source)
                        session.add(article)
                first = backfill_entities()
                second = backfill_entities()
                self.assertEqual(first["links"], 3)
                self.assertEqual(second["links"], 3)

            with Session(engine) as session:
                links = list(session.scalars(select(ArticleEntity)))
                self.assertEqual(len(links), 3)
                self.assertEqual({link.evidence_field for link in links}, {"source_body"})
                self.assertEqual({link.matched_alias for link in links}, {"Axon Enterprise", "ChatGPT"})
                axon = session.scalar(select(Entity).where(Entity.slug == "axon"))
                axon_article = session.scalar(select(Article).where(Article.source_url == "https://example.org/axon"))
                axon_article_id = axon_article.id
                self.assertEqual(len(axon.articles), 2)

            api_engine = create_engine(database_url)

            def session_override():
                with Session(api_engine) as api_session:
                    yield api_session

            app = create_app()
            app.dependency_overrides[get_session] = session_override
            with TestClient(app) as client:
                directory = client.get("/api/v1/entities?limit=1").json()
                self.assertEqual(len(directory["items"]), 1)
                self.assertIsNotNone(directory["next_cursor"])
                next_page = client.get(f"/api/v1/entities?limit=1&cursor={directory['next_cursor']}").json()
                self.assertEqual(len(next_page["items"]), 1)
                self.assertEqual({row["slug"] for row in directory["items"] + next_page["items"]},
                                 {"axon", "chatgpt"})
                self.assertEqual(client.get("/api/v1/entities?type=vendor").json()["items"][0]["slug"],
                                 "axon")
                listing = client.get("/api/v1/articles?period=all&entity=axon").json()
                self.assertEqual(len(listing["items"]), 2)
                self.assertIn(str(axon_article_id), [row["id"] for row in listing["items"]])
                first_article = client.get("/api/v1/articles?period=all&entity=axon&limit=1").json()
                self.assertIsNotNone(first_article["next_cursor"])
                page_cursor = first_article["next_cursor"]
                second_article = client.get(f"/api/v1/articles?period=all&entity=axon&limit=1&cursor={page_cursor}").json()
                self.assertEqual(len(second_article["items"]), 1)
                self.assertNotEqual(first_article["items"][0]["id"], second_article["items"][0]["id"])
                self.assertEqual(client.get(
                    f"/api/v1/articles?period=all&entity=chatgpt&limit=1&cursor={page_cursor}"
                ).status_code, 400)
                detail = client.get(f"/api/v1/articles/{axon_article_id}").json()
                self.assertEqual(detail["entities"][0]["slug"], "axon")

            with Session(engine) as session, session.begin():
                for article in session.scalars(select(Article).where(
                    Article.source_url.in_(("https://example.org/axon", "https://example.org/axon-2"))
                )):
                    article.deleted_at = datetime.now(UTC)
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/v1/entities?type=vendor").json()["items"], [])
                self.assertEqual(client.get("/api/v1/articles?period=all&entity=axon").json()["items"], [])
            api_engine.dispose()
            engine.dispose()
