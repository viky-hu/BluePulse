from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from bluepulse_backend.ingestion.adapters import (
    FetchedArticle,
    SourceAccessChallenge,
    SourceRateLimited,
    _get_json_or_text,
)
from bluepulse_backend.ingestion.llm import (
    MAX_TRANSLATION_CHARS, ModelAnalysisError, ModelConfig, NoticeAnalysis, _translation_chunks,
    analyze_source_article, translate_source_body,
)
from bluepulse_backend.ingestion.pipeline import (
    _article_from_item,
    reprocess_pending,
    run_ingestion,
    translate_pending,
)
from bluepulse_backend.ingestion.processing import has_explicit_technology, process_source_article
from bluepulse_backend.api import create_app, get_session
from bluepulse_backend.models import Article, Base, Entity, FeaturedEdition, Source, Topic


class IngestionProcessingTests(unittest.TestCase):
    def test_partial_detail_parse_is_visible_in_run_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{(Path(temp_dir) / 'test.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            with Session(engine) as session, session.begin():
                session.add(Source(
                    slug="ccgp-policing-tech", name="CCGP", adapter="ccgp_html",
                    base_url="https://www.ccgp.gov.cn/cggg/zygg/gkzb/", enabled=True,
                ))
            engine.dispose()

            def fetch(_source, *, known_urls, diagnostics):
                self.assertEqual(known_urls, set())
                diagnostics["detail_parse_failed"] = 1
                return [FetchedArticle(
                    url="https://www.ccgp.gov.cn/cggg/zygg/gkzb/202610/t20261001_123.htm",
                    title="公安智能项目", body="公安智能项目公告正文。" * 12,
                    language="zh", parse_status="full_text", processing_status="processed",
                    zh_summary="公安智能项目公告。",
                )]

            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                       side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.fetch_source", side_effect=fetch):
                    result = run_ingestion(source_slug="ccgp-policing-tech")
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["detail_parse_failed"], 1)
            self.assertEqual(result["source_partials"], 1)

    def test_archived_article_is_available_with_all_period_and_translation_backfill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{(Path(temp_dir) / 'test.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            with Session(engine) as session, session.begin():
                source = Source(
                    slug="nij-policing-tech", name="NIJ", base_url="https://nij.ojp.gov/library/articles/list",
                    adapter="nij_html", source_type="government", enabled=True,
                )
                session.add(source)
                session.flush()
                item = FetchedArticle(
                    url="https://nij.ojp.gov/topics/articles/body-cameras", title="Body cameras",
                    body="Police research on body cameras and public safety.",
                    published_at=datetime(2024, 1, 1, tzinfo=UTC), language="en",
                    parse_status="full_text", processing_status="processed",
                    zh_title="执法记录仪研究", zh_summary="一项警务研究。",
                )
                article = _article_from_item(item, source)
                session.add(article)
                session.flush()
                article_id = article.id
            engine.dispose()

            api_engine = create_engine(database_url)

            def session_override():
                with Session(api_engine) as api_session:
                    yield api_session

            app = create_app()
            app.dependency_overrides[get_session] = session_override
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/v1/articles").json()["items"], [])
                self.assertEqual(len(client.get("/api/v1/articles?period=all").json()["items"]), 1)
                detail = client.get(f"/api/v1/articles/{article_id}").json()
                self.assertEqual(detail["source_body"], item.body)
                self.assertIsNone(detail["zh_body"])
            api_engine.dispose()

            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                       side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.load_model_config",
                           return_value=ModelConfig("x", "x", "x")):
                    with patch("bluepulse_backend.ingestion.pipeline.translate_source_body",
                               return_value="警务执法记录仪研究。") as model:
                        result = translate_pending(source_slug="nij-policing-tech", limit=1)
            self.assertEqual(result["translated"], 1)
            self.assertEqual(model.call_count, 1)
            engine = create_engine(database_url)
            with Session(engine) as session:
                saved = session.get(Article, article_id)
                self.assertEqual(saved.source_body, item.body)
                self.assertEqual(saved.zh_body, "警务执法记录仪研究。")
            engine.dispose()

    def test_body_translation_keeps_chunks_in_order(self) -> None:
        chunks: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            import json

            payload = json.loads(request.content)
            chunk = payload["messages"][1]["content"]
            chunks.append(chunk)
            return httpx.Response(200, json={"choices": [{"message": {"content": f"译文{len(chunks)}"}}]})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            translated = translate_source_body(
                "A" * 2600, ModelConfig("https://example.test/v1", "test", "test"), client=client,
            )
        self.assertEqual([len(chunk) for chunk in chunks], [1000, 1000, 600])
        self.assertEqual(translated, "译文1\n\n译文2\n\n译文3")
        spaced = ("police technology " * 180).strip()
        split = _translation_chunks(spaced)
        self.assertEqual("".join(split), spaced)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in split))
        self.assertTrue(all(chunk.endswith(" ") for chunk in split[:-1]))
        sentences = ("The officer tested a camera. " * 90).strip()
        sentence_chunks = _translation_chunks(sentences)
        self.assertEqual("".join(sentence_chunks), sentences)
        self.assertTrue(all(chunk.endswith(". ") for chunk in sentence_chunks[:-1]))

    def test_truncated_translation_is_not_saved(self) -> None:
        response = httpx.Response(200, json={"choices": [{
            "message": {"content": "不完整译文"}, "finish_reason": "length",
        }]})
        with httpx.Client(transport=httpx.MockTransport(lambda _request: response)) as client:
            with self.assertRaisesRegex(ModelAnalysisError, "不完整内容"):
                translate_source_body("Police camera report.", ModelConfig("https://example.test/v1", "x", "x"),
                                      client=client)

    def test_translation_failure_keeps_relevant_article_and_original(self) -> None:
        source = Source(slug="nij", name="NIJ", adapter="nij_html", source_type="government")
        item = FetchedArticle(
            url="https://example.org/story", title="Police cameras", body="Original English body.",
            language="en", parse_status="full_text",
        )
        analysis = NoticeAnalysis(True, 0.9, "警用摄像头", "报道讨论警用摄像头。", ("policing",), 70)
        errors: list[str] = []
        with patch("bluepulse_backend.ingestion.processing.analyze_source_article", return_value=analysis):
            with patch("bluepulse_backend.ingestion.processing.translate_source_body",
                       side_effect=ModelAnalysisError("translation unavailable")):
                result = process_source_article(
                    item, source, ModelConfig("x", "x", "x"),
                    on_translation_error=lambda exc: errors.append(str(exc)),
                )
        self.assertEqual(result.processing_status, "processed")
        self.assertEqual(result.translation_status, "failed")
        self.assertEqual(result.body, item.body)
        self.assertIsNone(result.zh_body)
        self.assertEqual(errors, ["translation unavailable"])

    def test_long_english_body_skips_translation_without_failure(self) -> None:
        source = Source(slug="nij", name="NIJ", adapter="nij_html", source_type="government")
        item = FetchedArticle(
            url="https://example.org/long", title="Police technology", body="A" * (MAX_TRANSLATION_CHARS + 1),
            language="en", parse_status="full_text",
        )
        analysis = NoticeAnalysis(True, 0.9, "警务技术", "技术研究。", ("policing",), 70)
        errors: list[str] = []
        with patch("bluepulse_backend.ingestion.processing.analyze_source_article", return_value=analysis):
            with patch("bluepulse_backend.ingestion.processing.translate_source_body") as translate:
                result = process_source_article(
                    item, source, ModelConfig("x", "x", "x"),
                    on_translation_error=lambda exc: errors.append(str(exc)),
                )
        translate.assert_not_called()
        self.assertEqual(result.processing_status, "processed")
        self.assertEqual(result.translation_status, "too_long")
        self.assertEqual(result.body, item.body)
        self.assertIsNone(result.zh_body)
        self.assertEqual(errors, [])

    def test_gdelt_rate_limit_cooldown_persists_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{(Path(temp_dir) / 'test.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            with Session(engine) as session, session.begin():
                session.add(Source(
                    slug="gdelt-public-news", name="GDELT", base_url="https://api.gdeltproject.org/api/v2/doc/doc",
                    adapter="gdelt", enabled=True,
                ))
            engine.dispose()
            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                       side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.fetch_source",
                           side_effect=SourceRateLimited("HTTP 429")) as fetch:
                    first = run_ingestion(source_slug="gdelt-public-news")
                    second = run_ingestion(source_slug="gdelt-public-news")
                    third = run_ingestion(source_slug="gdelt-public-news")
            self.assertEqual(first["failures"][0]["error_class"], "SourceRateLimited")
            self.assertEqual(second["skips"], [{"source": "gdelt-public-news",
                                                 "reason": "rate_limit_cooldown"}])
            self.assertEqual(third["source_skipped"], 1)
            self.assertEqual(fetch.call_count, 1)

    def test_rss_requires_explicit_technology_evidence(self) -> None:
        source = Source(slug="police1-recent", name="Police1", adapter="rss", source_type="news")
        analysis = NoticeAnalysis(True, 0.9, "警务技术", "技术应用。", ("policing",), 75)
        plain = FetchedArticle(
            url="https://example.org/plain", title="Campus policing mission has changed",
            body="Agencies discuss staffing and training.", language="en", parse_status="summary_only",
        )
        technical = FetchedArticle(
            url="https://example.org/alpr", title="Police test license plate readers",
            body="Officers will evaluate ALPR devices.", language="en", parse_status="summary_only",
        )
        self.assertFalse(has_explicit_technology(plain))
        self.assertTrue(has_explicit_technology(technical))
        with patch("bluepulse_backend.ingestion.processing.analyze_source_article", return_value=analysis):
            self.assertEqual(process_source_article(plain, source, ModelConfig("x", "x", "x")).processing_status,
                             "irrelevant")
            self.assertEqual(process_source_article(technical, source, ModelConfig("x", "x", "x")).processing_status,
                             "processed")

    def test_backfill_audits_already_processed_rss_articles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{(Path(temp_dir) / 'test.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            with Session(engine) as session, session.begin():
                source = Source(
                    slug="police1-recent", name="Police1", base_url="https://example.org/rss",
                    adapter="rss", enabled=True,
                )
                session.add(source)
                session.flush()
                for url, title in (
                    ("https://example.org/plain", "Police training changes"),
                    ("https://example.org/technical", "Police test ALPR cameras"),
                ):
                    item = FetchedArticle(
                        url=url, title=title, processing_status="processed",
                        parse_status="summary_only", body="Source summary for editorial review.",
                        featured_candidate=url.endswith("technical"),
                    )
                    session.add(_article_from_item(item, source))
            engine.dispose()
            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                       side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.load_model_config",
                           return_value=ModelConfig("x", "x", "x")):
                    result = reprocess_pending(source_slug="police1-recent", limit=1)
            self.assertEqual(result["examined"], 0)
            self.assertEqual(result["rejected_existing"], 1)
            engine = create_engine(database_url)
            with Session(engine) as session:
                articles = {article.source_url: article for article in session.scalars(select(Article))}
                self.assertEqual(articles["https://example.org/plain"].processing_status, "irrelevant")
                self.assertEqual(articles["https://example.org/technical"].processing_status, "processed")
                edition = session.scalar(select(FeaturedEdition))
                self.assertEqual([slot.article.source_url for slot in edition.slots],
                                 ["https://example.org/technical"])
            engine.dispose()

    def test_missing_model_id_reports_configuration_error_without_retry(self) -> None:
        calls = 0

        def respond(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(404)

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(ModelAnalysisError, "模型 ID"):
                analyze_source_article(
                    "https://example.org/work", "Police technology study", None,
                    "academic", "metadata_only", ModelConfig("https://example.test/v1", "test", "old"),
                    client=client,
                )
        self.assertEqual(calls, 1)

    def test_model_retries_transient_protocol_error_once(self) -> None:
        calls = 0

        def respond(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            self.assertNotIn("source_url", request.content.decode("utf-8"))
            if calls == 1:
                raise httpx.RemoteProtocolError("temporary disconnect")
            return httpx.Response(200, json={"choices": [{"message": {"content": (
                '{"relevant":true,"relevance":0.9,"short_title":"警务技术研究",'
                '"summary":"研究警务技术应用。","topics":["policing","research"],'
                '"importance_score":65}'
            )}}]})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with patch("bluepulse_backend.ingestion.llm.sleep"):
                result = analyze_source_article(
                    "https://example.org/work", "Police technology study", "Police research",
                    "academic", "abstract_only", ModelConfig("https://example.test/v1", "test", "test"),
                    client=client,
                )
        self.assertEqual(calls, 2)
        self.assertTrue(result.relevant)

    def test_deepseek_reasoning_model_requests_json_with_sufficient_output_budget(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            import json

            payload = json.loads(request.content)
            self.assertEqual(payload["max_tokens"], 3000)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
                "content": ('{"relevant":true,"relevance":0.9,"short_title":"警用无人机研究",'
                            '"summary":"研究警用无人机应用。","topics":["policing"],'
                            '"importance_score":70}'),
                "reasoning_content": "internal reasoning",
            }}]})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result = analyze_source_article(
                "https://example.org/work", "Police drone study", "Police use drones.",
                "academic", "abstract_only", ModelConfig("https://example.test/v1", "test", "DeepSeek-V4.1-Flash"),
                client=client,
            )
        self.assertTrue(result.relevant)

    def test_truncated_reasoning_analysis_is_not_accepted(self) -> None:
        response = httpx.Response(200, json={"choices": [{
            "finish_reason": "length", "message": {"content": "{}", "reasoning_content": "thinking"},
        }]})
        with httpx.Client(transport=httpx.MockTransport(lambda _request: response)) as client:
            with self.assertRaisesRegex(ModelAnalysisError, "token 上限"):
                analyze_source_article(
                    "https://example.org/work", "Police drone study", "Police use drones.",
                    "academic", "abstract_only", ModelConfig("https://example.test/v1", "test", "DeepSeek-V4.1-Flash"),
                    client=client,
                )

    def test_waf_challenge_is_not_treated_as_rss(self) -> None:
        source = Source(
            slug="police1-recent", name="Police1", base_url="https://www.police1.com/recently-published.rss",
            adapter="rss", config={"allowed_hosts": ["www.police1.com"]},
        )
        requests: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(202, headers={"x-amzn-waf-action": "challenge"})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        try:
            with patch("bluepulse_backend.ingestion.adapters.httpx.Client", return_value=client):
                with self.assertRaises(SourceAccessChallenge):
                    _get_json_or_text(source)
        finally:
            client.close()
        self.assertEqual(len(requests), 1)

    def test_rate_limit_does_not_retry_immediately(self) -> None:
        source = Source(
            slug="gdelt-public-news", name="GDELT", base_url="https://api.gdeltproject.org/api/v2/doc/doc",
            adapter="gdelt", config={"allowed_hosts": ["api.gdeltproject.org"]},
        )
        requests: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(429, headers={"Retry-After": "60"})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        try:
            with patch("bluepulse_backend.ingestion.adapters.httpx.Client", return_value=client):
                with self.assertRaises(SourceRateLimited):
                    _get_json_or_text(source)
        finally:
            client.close()
        self.assertEqual(len(requests), 1)

    def test_new_items_are_analyzed_once_and_only_relevant_items_are_featured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{(Path(temp_dir) / 'test.db').as_posix()}"
            engine = create_engine(database_url)
            Base.metadata.create_all(engine)
            source = Source(
                slug="openalex-policing-tech", name="OpenAlex", base_url="https://api.openalex.org/works",
                adapter="openalex", source_type="academic", region="foreign", language="en",
                topics=["research"], config={"allowed_hosts": ["api.openalex.org"]},
                enabled=True,
            )
            old = FetchedArticle(url="https://example.org/old", title="Old pending item", language="en")
            with Session(engine) as session, session.begin():
                session.add(source)
                session.add(Topic(slug="research", name_zh="研究", name_en="Research", enabled=True))
                session.add(Topic(slug="policing", name_zh="警务", name_en="Policing", enabled=True))
                session.add(Entity(slug="axon", name="Axon", entity_type="vendor",
                                   aliases=["Axon Enterprise"], enabled=True))
                session.flush()
                session.add(_article_from_item(old, source))
            engine.dispose()

            now = datetime.now(UTC)
            good = FetchedArticle(
                url="https://example.org/police-ai", title="Police AI research",
                body="Axon Enterprise studied AI for police work",
                published_at=now, language="en", parse_status="abstract_only",
            )
            bad = FetchedArticle(
                url="https://example.org/unrelated", title="Oil and metaphor study", body="Literary analysis",
                published_at=now, language="en", parse_status="abstract_only",
            )
            relevant = NoticeAnalysis(True, 0.94, "警务人工智能研究", "研究警务工作中的人工智能应用。", ("policing", "research"), 70, True, "具体警务人工智能研究提供新方法。")
            irrelevant = NoticeAnalysis(False, 0.02, "", "", (), 0)

            def analyze(_url: str, title: str, *_args: object) -> NoticeAnalysis:
                return irrelevant if "Oil" in title else relevant

            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine", side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.fetch_source", return_value=[old, good, bad]):
                    with patch("bluepulse_backend.ingestion.pipeline.load_model_config", return_value=ModelConfig("https://example.test/v1", "test", "test")):
                        with patch("bluepulse_backend.ingestion.processing.analyze_source_article", side_effect=analyze) as model:
                            first = run_ingestion(source_slug="openalex-policing-tech")
                            second = run_ingestion(source_slug="openalex-policing-tech")
            self.assertEqual(first["status"], "succeeded")
            self.assertEqual(first["inserted"], 2)
            self.assertEqual(first["duplicates"], 1)
            self.assertEqual(first["irrelevant"], 1)
            self.assertEqual(first["model_calls"], 2)
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(second["duplicates"], 3)
            self.assertEqual(model.call_count, 2)

            engine = create_engine(database_url)
            with Session(engine) as session:
                articles = list(session.scalars(select(Article)))
                self.assertEqual(len(articles), 3)
                self.assertEqual({article.processing_status for article in articles},
                                 {"pending_model", "processed", "irrelevant"})
                processed_article = next(article for article in articles if article.processing_status == "processed")
                self.assertEqual([entity.slug for entity in processed_article.entities], ["axon"])
                editions = list(session.scalars(select(FeaturedEdition).order_by(FeaturedEdition.generated_at)))
                self.assertEqual(len(editions[-1].slots), 1)
                self.assertEqual(editions[-1].slots[0].article.processing_status, "processed")
                irrelevant_id = next(article.id for article in articles
                                     if article.processing_status == "irrelevant")
                pending_id = next(article.id for article in articles
                                  if article.processing_status == "pending_model")
            engine.dispose()

            api_engine = create_engine(database_url)

            def session_override():
                with Session(api_engine) as api_session:
                    yield api_session

            app = create_app()
            app.dependency_overrides[get_session] = session_override
            with TestClient(app) as client:
                listing = client.get("/api/v1/articles")
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(len(listing.json()["items"]), 1)
                self.assertEqual(listing.json()["items"][0]["processing_status"], "processed")
                self.assertEqual(client.get(f"/api/v1/articles/{irrelevant_id}").status_code, 404)
                self.assertEqual(client.get(f"/api/v1/articles/{pending_id}").status_code, 404)
            api_engine.dispose()

            with patch("bluepulse_backend.ingestion.pipeline.create_database_engine", side_effect=lambda: create_engine(database_url)):
                with patch("bluepulse_backend.ingestion.pipeline.load_model_config", return_value=ModelConfig("https://example.test/v1", "test", "test")):
                    with patch("bluepulse_backend.ingestion.processing.analyze_source_article", return_value=relevant):
                        backfill = reprocess_pending(source_slug="openalex-policing-tech", limit=1)
            self.assertEqual(backfill["processed"], 0)
            engine = create_engine(database_url)
            with Session(engine) as session:
                updated = session.scalar(select(Article).where(Article.source_url == old.url))
                self.assertEqual(updated.processing_status, "pending_model")
                self.assertIsNone(updated.zh_summary)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
