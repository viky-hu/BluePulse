from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from bluepulse_backend.api import create_app
from bluepulse_backend.db import Base, make_engine, make_session_factory
from bluepulse_backend.models import AnalysisAttempt, Discovery, Material, MaterialRevision, Source, Topic
from bluepulse_backend.pipeline import (
    AnalysisResult, Candidate, MockAnalyzer, MockSourceAdapter, UnknownOutcome,
    canonical_url, ingest, process_pending,
)
from bluepulse_backend.publication import create_featured_edition
from bluepulse_backend.operations import source_funnel


def setup(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    app = create_app(url)
    return factory, TestClient(app)


def make_source(session, *, slug="govuk", excerpt=True, full_text=False):
    source = Source(slug=slug, name=slug.upper(), region="foreign", country_code="GB",
                    language="en", source_type="official", topics=["policing"],
                    allowed_hosts=["example.gov.uk"], excerpt_allowed=excerpt,
                    full_text_allowed=full_text)
    session.add(source)
    session.commit()
    return source


def candidate(name: str, *, body="Original evidence text. " * 16, when=None):
    return Candidate(url=f"https://example.gov.uk/{name}?utm_source=test", title=f"Original {name}",
                     body=body, published_at=when or datetime.now(UTC) - timedelta(hours=1),
                     language="en")


def result(name: str, *, relevant=True, candidate=True):
    return AnalysisResult(relevant=relevant, title_zh=f"中文 {name}",
                          summary_zh=f"依据原文整理的 {name} 摘要" if relevant else None,
                          topics=("policing",), importance_score=72,
                          featured_candidate=candidate, body_zh=None)


def test_mock_chain_revision_api_and_withdrawal(tmp_path):
    factory, client = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        session.add(Topic(slug="policing", name_zh="警务应用", name_en="Policing"))
        session.commit()
        fixtures = [candidate("one"), candidate("two"), candidate("three")]
        run = ingest(session, source, MockSourceAdapter(fixtures))
        assert run.status == "completed" and run.candidate_count == 3
        assert session.scalar(select(func.count()).select_from(Material)) == 3
        again = ingest(session, source, MockSourceAdapter(fixtures))
        assert session.scalar(select(func.count()).select_from(MaterialRevision)) == 3
        assert {d.outcome for d in session.scalars(select(Discovery).where(Discovery.run_id == again.id))} == {"duplicate"}
        answers = {canonical_url(item.url, source.allowed_hosts): result(item.title) for item in fixtures}
        assert process_pending(session, MockAnalyzer(answers)) == {"applied": 3, "failed": 0, "unknown": 0}
        funnel = source_funnel(session, run.id)
        assert funnel["discoveries"] == {"new": 3}
        assert funnel["current_public"] == 3
        articles = session.scalars(select(Material).order_by(Material.id)).all()
        article_ids = [row.id for row in articles]
        assert all(UUID(value) for value in article_ids)
        articles[0].grouping_status = "complete"
        session.commit()
        create_featured_edition(session, [articles[0].id])

    assert client.get("/api/v1/health/ready").json() == {"status": "ready"}
    assert len(client.get("/api/v1/taxonomy").json()["items"]) == 1
    assert len(client.get("/api/v1/sources").json()["items"]) == 1
    first = client.get("/api/v1/articles?period=all&topic=policing&limit=2", headers={"X-Request-ID": "test-123"})
    assert first.status_code == 200 and first.headers["x-request-id"] == "test-123"
    assert len(first.json()["items"]) == 2
    assert first.json()["items"][0]["source"]["slug"] == "govuk"
    cursor = first.json()["next_cursor"]
    assert cursor
    second = client.get("/api/v1/articles", params={"period": "all", "topic": "policing", "limit": 2, "cursor": cursor})
    assert len(second.json()["items"]) == 1 and second.json()["next_cursor"] is None
    assert client.get("/api/v1/articles", params={"period": "7d", "topic": "policing", "limit": 2, "cursor": cursor}).json()["error"]["code"] == "invalid_cursor"
    assert client.get("/api/v1/articles", params={"q": "中文", "period": "all"}).json()["items"]
    assert client.get("/api/v1/articles", params={"sort": "importance", "period": "all"}).status_code == 200
    assert client.get("/api/v1/articles", params={"period": "all", "region": "domestic"}).json()["items"] == []
    assert client.get("/api/v1/articles?limit=0").status_code == 422
    assert len(client.get("/api/v1/home/recently-collected").json()["items"]) == 3
    assert len(client.get("/api/v1/home/featured").json()["items"]) == 1
    detail = client.get(f"/api/v1/articles/{article_ids[0]}").json()
    assert detail["source_body"] is None and detail["zh_body"] is None  # license gate
    assert detail["quality_status"] == "model_processed"
    assert detail["translation_status"] == "pending"
    assert client.get("/api/v1/entities").json()["items"] == []

    with factory() as session:
        article = session.get(Material, article_ids[0])
        article.withdrawn = True
        session.commit()
    assert client.get(f"/api/v1/articles/{article_ids[0]}").status_code == 404
    assert client.get("/api/v1/home/featured").json()["items"] == []
    assert not client.get("/api/v1/articles/availability", params={"ids": article_ids[0]}).json()["items"][0]["available"]
    assert len(client.get("/api/v1/articles?period=all").json()["items"]) == 2


def test_targeted_analysis_leaves_other_material_pending(tmp_path):
    factory, _ = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        ingest(session, source, MockSourceAdapter([candidate("one"), candidate("two")]))
        rows = session.scalars(select(Material).order_by(Material.source_title)).all()
        target = rows[1]
        answer = {target.canonical_url: result("two")}
        assert process_pending(session, MockAnalyzer(answer), material_id=target.id,
                               max_items=1) == {"applied": 1, "failed": 0, "unknown": 0}
        session.refresh(rows[0])
        assert rows[0].state == "analysis_pending"
        assert target.state == "publication_pool"
        assert session.scalar(select(func.count()).select_from(AnalysisAttempt)) == 1


def test_revision_reprocess_and_source_pause(tmp_path):
    factory, client = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        one = candidate("revision")
        ingest(session, source, MockSourceAdapter([one]))
        key = canonical_url(one.url, source.allowed_hosts)
        process_pending(session, MockAnalyzer({key: result("v1")}))
        article = session.scalar(select(Material))
        old_id = article.id
        source.enabled = False
        session.commit()
        assert client.get(f"/api/v1/articles/{old_id}").status_code == 200
        source.enabled = True
        changed = Candidate(url=one.url, title=one.title, body="Corrected source body. " * 16,
                            published_at=one.published_at, language="en")
        ingest(session, source, MockSourceAdapter([changed]))
        session.refresh(article)
        assert article.revision == 2 and not article.public
        assert client.get(f"/api/v1/articles/{old_id}").status_code == 404
        process_pending(session, MockAnalyzer({key: result("v2")}))
        assert client.get(f"/api/v1/articles/{old_id}").json()["title"] == "中文 v2"
        assert session.scalar(select(func.count()).select_from(MaterialRevision)) == 2
        assert session.scalar(select(func.count()).select_from(AnalysisAttempt)) == 2


def test_unknown_receipt_and_saved_result_recovery(tmp_path):
    factory, _ = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        one = candidate("unknown")
        ingest(session, source, MockSourceAdapter([one]))
        calls = []

        class Uncertain:
            def analyze(self, material):
                calls.append(material.id)
                raise UnknownOutcome()

        assert process_pending(session, Uncertain())["unknown"] == 1
        assert process_pending(session, Uncertain()) == {"applied": 0, "failed": 0, "unknown": 0}
        assert len(calls) == 1
        material = session.scalar(select(Material))
        assert material.state == "receipt_unknown" and not material.public
        # A known persisted response after a crash may be applied without a second provider call.
        material.state = "analysis_pending"
        saved = session.scalar(select(AnalysisAttempt))
        saved.status = "result_saved"
        saved.result = {"relevant": True, "title_zh": "恢复", "summary_zh": "已存响应",
                        "topics": ["policing"], "importance_score": 60,
                        "featured_candidate": False, "body_zh": None}
        session.commit()
        assert process_pending(session, Uncertain())["applied"] == 1
        assert len(calls) == 1


def test_started_attempt_is_not_resent_after_restart(tmp_path):
    factory, _ = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        ingest(session, source, MockSourceAdapter([candidate("interrupted")]))
        material = session.scalar(select(Material))
        session.add(AnalysisAttempt(material_id=material.id, revision=1,
                                    input_version="mock-contract-v1", attempt=1, status="started"))
        session.commit()
        class NoCall:
            def analyze(self, material):
                raise AssertionError("must not resend uncertain request")
        assert process_pending(session, NoCall())["unknown"] == 1
        assert material.state == "receipt_unknown"


def test_rejected_and_historical_items_never_fill_featured(tmp_path):
    factory, client = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        historical = candidate("old", when=datetime.now(UTC) - timedelta(days=30))
        bad = Candidate(url="http://127.0.0.1/private", title="private")
        run = ingest(session, source, MockSourceAdapter([historical, bad]))
        assert run.status == "partial"
        assert session.scalar(select(Discovery.reason_code).where(Discovery.outcome == "rejected")) == "host_not_allowed"
        key = canonical_url(historical.url, source.allowed_hosts)
        process_pending(session, MockAnalyzer({key: result("old")}))
        article = session.scalar(select(Material))
        assert article.timeline_kind == "historical"
        article.grouping_status = "complete"
        session.commit()
        try:
            create_featured_edition(session, [article.id])
            assert False, "historical item should be rejected"
        except ValueError:
            pass
        assert client.get("/api/v1/articles?period=24h").json()["items"] == []
        assert len(client.get("/api/v1/articles?period=all").json()["items"]) == 1


def test_empty_contract_and_unavailable_database(tmp_path):
    factory, client = setup(tmp_path)
    document = client.get("/openapi.json").json()
    paths = document["paths"]
    expected = {
        "/api/v1/health/live", "/api/v1/health/ready", "/api/v1/sources",
        "/api/v1/taxonomy", "/api/v1/entities", "/api/v1/home/featured",
        "/api/v1/home/recently-collected", "/api/v1/articles",
        "/api/v1/articles/availability", "/api/v1/articles/{article_id}",
    }
    assert expected <= set(paths)
    article_schema = paths["/api/v1/articles"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert article_schema["$ref"].endswith("ArticleListOut")
    assert "ArticleCardOut" in document["components"]["schemas"]
    assert client.get("/api/v1/articles").json() == {"items": [], "next_cursor": None, "limit": 20}
    assert client.get("/api/v1/home/featured").json()["generated_at"] is None
    assert client.get("/api/v1/articles/availability?ids=").json() == {"items": []}
    assert client.get("/api/v1/articles/availability?ids=bad").status_code == 422
    assert client.get("/api/v1/articles/not-a-uuid").status_code == 422
    missing = TestClient(create_app(f"sqlite:///{(tmp_path / 'uninitialized.db').as_posix()}"))
    assert missing.get("/api/v1/health/live").status_code == 200
    response = missing.get("/api/v1/health/ready")
    assert response.status_code == 503 and response.json()["error"]["code"] == "database_unavailable"


def test_failed_analysis_retry_and_source_failure(tmp_path):
    factory, _ = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        class BrokenAdapter:
            def candidates(self):
                raise RuntimeError("fixture outage")
        failed_run = ingest(session, source, BrokenAdapter())
        assert failed_run.status == "failed" and failed_run.error_code == "adapter_failed"
        one = candidate("retry")
        good_run = ingest(session, source, MockSourceAdapter([one]))
        assert good_run.status == "completed"
        assert process_pending(session, MockAnalyzer({}))["failed"] == 1
        material = session.scalar(select(Material))
        assert material.state == "analysis_failed" and not material.public
        key = canonical_url(one.url, source.allowed_hosts)
        assert process_pending(session, MockAnalyzer({key: result("retry")}), retry_failed=True)["applied"] == 1
        assert material.public
        assert source_funnel(session, good_run.id)["analysis_status"] == {"failed": 1, "applied": 1}


def test_untrusted_future_time_is_not_presented_as_recent(tmp_path):
    factory, client = setup(tmp_path)
    with factory() as session:
        source = make_source(session)
        item = candidate("future", when=datetime.now(UTC) + timedelta(days=2))
        ingest(session, source, MockSourceAdapter([item]))
        material = session.scalar(select(Material))
        assert material.timeline_kind == "unknown" and material.published_at is None
        revision = session.scalar(select(MaterialRevision))
        assert revision.published_at is not None  # retain source evidence
        key = canonical_url(item.url, source.allowed_hosts)
        process_pending(session, MockAnalyzer({key: result("future")}))
        assert client.get("/api/v1/articles?period=24h").json()["items"] == []
        assert client.get("/api/v1/articles?period=all").json()["items"][0]["published_at"] is None


def test_abstract_is_not_auto_published_even_with_legacy_source_policy(tmp_path):
    factory, client = setup(tmp_path)
    with factory() as session:
        source = make_source(session, excerpt=True)
        item = Candidate(url="https://example.gov.uk/abstract", title="Technology abstract",
                         summary="A specific communication technology was tested.", language="en",
                         published_at=datetime.now(UTC) - timedelta(hours=1))
        ingest(session, source, MockSourceAdapter([item]))
        key = canonical_url(item.url, source.allowed_hosts)
        process_pending(session, MockAnalyzer({key: result("abstract")}))
        material = session.scalar(select(Material))
        assert not material.public and client.get("/api/v1/articles?period=all").json()["items"] == []
        source.min_body_status = "abstract_only"
        material.state = "analysis_pending"
        session.commit()
        assert process_pending(session, MockAnalyzer({key: result("abstract")}))["applied"] == 1
        assert not material.public and client.get("/api/v1/articles?period=all").json()["items"] == []
        source.min_body_status = "full_text"
        session.commit()
        assert client.get(f"/api/v1/articles/{material.id}").status_code == 404
        assert client.get("/api/v1/articles?period=all").json()["items"] == []
