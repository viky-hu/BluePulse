"""Offline acceptance: one source item reaches the public API without touching dev data."""

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
from bluepulse_backend.ingestion.adapters import FetchedArticle, FetchedMedia
from bluepulse_backend.ingestion.llm import ModelConfig, NoticeAnalysis
from bluepulse_backend.ingestion.pipeline import run_ingestion
from bluepulse_backend.models import Article, ArticleMedia, Base, Source, Topic
from scripts.content_smoke import _PageText


class FullFlowTests(unittest.TestCase):
    def test_frontend_smoke_checks_visible_heading_not_hydration_payload(self) -> None:
        page = _PageText()
        page.feed('<main data-reading-page><h1>警用无人机现场测绘试点</h1></main>'
                  '<script>other title</script>')
        self.assertTrue(page.reading_page)
        self.assertEqual("".join(page.heading_parts), "警用无人机现场测绘试点")

    def test_relevant_article_from_collection_to_public_cards_and_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_url = f"sqlite:///{(Path(temporary) / 'flow.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            with Session(engine) as session, session.begin():
                session.add(Source(
                    slug="govuk-policing-tech", name="GOV.UK", adapter="govuk_api",
                    base_url="https://www.gov.uk/api/search.json", enabled=True,
                    source_type="government", country_code="GB", region="foreign",
                ))
                session.add(Topic(slug="policing", name_zh="警务", name_en="Policing"))
            engine.dispose()
            title = "Police drone technology trial for scene mapping"
            source_body = "Police officers used drone technology to map investigation scenes. " * 12
            item = FetchedArticle(
                url="https://www.gov.uk/government/news/police-drone-scene-mapping",
                title=title, body=source_body, language="en", country_code="GB",
                published_at=datetime.now(UTC), parse_status="full_text",
                media=(FetchedMedia(kind="image",
                                    url="https://assets.publishing.service.gov.uk/media/drone.jpg",
                                    alt_text="Police drone"),),
            )
            analysis = NoticeAnalysis(
                relevant=True, relevance=0.95, short_title="警用无人机现场测绘试点",
                summary="警方将无人机用于勘查现场测绘。", topics=("policing",),
                importance_score=78, featured_candidate=True,
                featured_reason="有明确的警务现场应用场景。",
            )
            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                       side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.fetch_source", return_value=[item]):
                    with patch("bluepulse_backend.ingestion.pipeline.load_model_config",
                               return_value=ModelConfig("https://example.test/v1", "test", "test")):
                        with patch("bluepulse_backend.ingestion.processing.analyze_source_article",
                                   return_value=analysis) as analyze:
                            with patch("bluepulse_backend.ingestion.processing.translate_source_body",
                                       return_value="警方使用无人机技术对勘查现场进行测绘。"):
                                result = run_ingestion(source_slug="govuk-policing-tech")
            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["model_calls"], 1)
            analyze.assert_called_once()

            api_engine = create_engine(database_url)

            def session_override():
                with Session(api_engine) as session:
                    yield session

            app = create_app()
            app.dependency_overrides[get_session] = session_override
            try:
                with TestClient(app) as client:
                    cards = client.get("/api/v1/articles?period=7d").json()["items"]
                    self.assertEqual(len(cards), 1)
                    card = cards[0]
                    self.assertEqual(card["title"], analysis.short_title)
                    self.assertEqual(card["summary"], analysis.summary)
                    self.assertEqual(card["media_preview"]["alt_text"], "Police drone")
                    self.assertEqual(card["topics"], ["policing"])
                    detail = client.get(f"/api/v1/articles/{card['id']}").json()
                    self.assertEqual(detail["source_body"], source_body)
                    self.assertEqual(detail["zh_body"], "警方使用无人机技术对勘查现场进行测绘。")
                    self.assertEqual(detail["url"], item.url)
                    self.assertEqual(detail["media"][0]["url"], item.media[0].url)
                    featured = client.get("/api/v1/home/featured").json()["items"]
                    self.assertEqual(featured[0]["article"]["id"], card["id"])
                    self.assertEqual(featured[0]["featured_reason"], analysis.featured_reason)
                    self.assertEqual(featured[0]["article"]["media_preview"], card["media_preview"])
                with Session(api_engine) as session:
                    self.assertEqual(str(session.scalar(select(Article.id))), card["id"])
                    self.assertEqual(session.scalar(select(ArticleMedia.url)), item.media[0].url)
            finally:
                api_engine.dispose()

    def test_title_only_candidate_is_counted_but_not_stored_when_policy_disables_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_url = f"sqlite:///{(Path(temporary) / 'metadata.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            with Session(engine) as session, session.begin():
                session.add(Source(
                    slug="gdelt-public-news", name="GDELT", adapter="gdelt",
                    base_url="https://api.gdeltproject.org/api/v2/doc/doc", enabled=True,
                    config={"store_metadata_only": False},
                ))
            engine.dispose()
            item = FetchedArticle(url="https://example.org/one", title="Police drone story")
            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                       side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.fetch_source", return_value=[item]):
                    with patch("bluepulse_backend.ingestion.pipeline.load_model_config", return_value=None):
                        result = run_ingestion(source_slug="gdelt-public-news")
            self.assertEqual(result["discovered"], 1)
            self.assertEqual(result["metadata_skipped"], 1)
            self.assertEqual(result["inserted"], 0)
            engine = create_engine(database_url)
            with Session(engine) as session:
                self.assertIsNone(session.scalar(select(Article.id)))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
