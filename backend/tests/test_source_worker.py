from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bluepulse_backend import source_worker
from bluepulse_backend.api import create_app
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.live_sources import SourceFetchError
from bluepulse_backend.models import Material, Source, SourceRun
from bluepulse_backend.pipeline import AnalysisResult, Candidate, MockAnalyzer
from bluepulse_backend.publication import evidence_allowed


def test_transient_fetch_retry_preserves_both_runs_and_auto_publishes_with_permission(tmp_path, monkeypatch):
    address = f"sqlite:///{(tmp_path / 'worker.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    slug = "nist-public-safety"
    spec = source_worker.SOURCES[slug]
    url = f"https://{spec.host}/news-events/news/fixture"
    calls = []

    class Adapter:
        diagnostics = {"detail_attempts": 1, "detail_body": 1}

        def candidates(self):
            calls.append(1)
            if len(calls) == 1:
                raise SourceFetchError("transport_error")
            return [Candidate(url=url, title="Public safety radio test",
                              body="A documented police radio interoperability trial. " * 10,
                              published_at=datetime(2026, 11, 4, tzinfo=UTC), language="en")]

    monkeypatch.setattr(source_worker, "build_adapter", lambda *_args, **_kwargs: Adapter())
    answer = MockAnalyzer({url: AnalysisResult(
        relevant=True, title_zh="警用通信试验", summary_zh="原文记录警用通信互通试验。",
        topics=("practice",), importance_score=70)})
    with Session(engine) as session:
        session.add(Source(slug=slug, name=spec.name, region=spec.region,
                           country_code=spec.country_code, language=spec.language,
                           source_type=spec.source_type, topics=[], allowed_hosts=[spec.host],
                           enabled=True, excerpt_allowed=True, full_text_allowed=False))
        session.commit()
        report = source_worker.run_cycle(
            session, lambda: nullcontext(None), source_slugs=[slug], analyzer=answer,
            model_remaining=1, retry_delay=0, sleeper=lambda _: None)
        assert len(report["sources"][0]["attempts"]) == 2
        assert [row["status"] for row in report["sources"][0]["attempts"]] == ["failed", "completed"]
        assert report["sources"][0]["attempts"][0]["error_code"] == "transport_error"
        assert report["model_used"] == 1
        assert report["sources"][0]["attempts"][-1]["current_public"] == 1
        assert report["sources"][0]["attempts"][-1]["analysis_status"] == {"applied": 1}
        assert session.scalar(select(Material)).public
        assert session.scalar(select(func.count()).select_from(SourceRun)) == 2
        with TestClient(create_app(address)) as client:
            items = client.get("/api/v1/articles?period=all&topic=practice").json()["items"]
            assert len(items) == 1
            assert client.get(f"/api/v1/articles/{items[0]['id']}").status_code == 200
        source = session.scalar(select(Source).where(Source.slug == slug))
        source.excerpt_allowed = False
        session.commit()
        hidden = source_worker.run_cycle(
            session, lambda: nullcontext(None), source_slugs=[slug],
            retry_attempts=0, model_remaining=0)
        assert hidden["sources"][0]["permission_changes"] == {"released": 0, "hidden": 1}
        assert not session.scalar(select(Material)).public
        source.excerpt_allowed = True
        session.commit()
        released = source_worker.run_cycle(
            session, lambda: nullcontext(None), source_slugs=[slug],
            retry_attempts=0, model_remaining=0)
        assert released["sources"][0]["permission_changes"] == {"released": 1, "hidden": 0}
        assert released["model_used"] == 0 and session.scalar(select(Material)).public
    engine.dispose()


def test_robot_disallow_never_retries(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{(tmp_path / 'blocked.db').as_posix()}")
    Base.metadata.create_all(engine)
    calls = []

    class Adapter:
        diagnostics = {"robots_status": 200}

        def candidates(self):
            calls.append(1)
            raise SourceFetchError("robots_disallowed")

    monkeypatch.setattr(source_worker, "build_adapter", lambda *_args, **_kwargs: Adapter())
    with Session(engine) as session:
        report = source_worker.run_cycle(
            session, lambda: nullcontext(None), source_slugs=["nist-public-safety"],
            retry_attempts=3, retry_delay=0, sleeper=lambda _: None)
        assert len(calls) == 1
        assert len(report["sources"][0]["attempts"]) == 1
        assert report["sources"][0]["attempts"][0]["error_code"] == "robots_disallowed"
    engine.dispose()


def test_public_evidence_needs_300_non_whitespace_characters():
    short = Material(source_body="a" * 299, body_status="full_text")
    enough = Material(source_body="a" * 300, body_status="full_text")
    assert not evidence_allowed(short)
    assert evidence_allowed(enough)
    enough.body_status = "abstract_only"
    assert not evidence_allowed(enough)


def test_short_body_does_not_spend_model_call(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{(tmp_path / 'short.db').as_posix()}")
    Base.metadata.create_all(engine)
    slug = "nist-public-safety"
    spec = source_worker.SOURCES[slug]

    class Adapter:
        diagnostics = {}

        def candidates(self):
            return [Candidate(url=f"https://{spec.host}/news-events/news/short",
                              title="Short notice", body="Brief notice.")]

    class UnexpectedAnalyzer:
        def analyze(self, material):
            raise AssertionError("short body must not call the model")

    monkeypatch.setattr(source_worker, "build_adapter", lambda *_args, **_kwargs: Adapter())
    with Session(engine) as session:
        report = source_worker.run_cycle(
            session, lambda: nullcontext(None), source_slugs=[slug],
            retry_attempts=0, analyzer=UnexpectedAnalyzer(), model_remaining=1)
        assert report["model_used"] == 0
        assert report["sources"][0]["processing"]["short_body"] == 1
        assert not session.scalar(select(Material)).public
    engine.dispose()


def test_worker_report_records_request_paths_and_statuses(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'trace.db').as_posix()}")
    Base.metadata.create_all(engine)
    detail = "https://www.nist.gov/news-events/news/2026/10/radio-test"
    feed = ("<rss><channel><item><title>Public safety radio test</title>"
            f"<link>{detail}</link></item></channel></rss>")

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path.endswith("rss.xml"):
            return httpx.Response(200, text=feed)
        return httpx.Response(200, text=(
            "<div class='text-with-summary'><p>Documented radio interoperability results. "
            + "A" * 320 + "</p></div>"))

    with Session(engine) as session:
        report = source_worker.run_cycle(
            session, lambda: httpx.Client(transport=httpx.MockTransport(handler)),
            source_slugs=["nist-public-safety"], max_items=1, retry_attempts=0)
        attempt = report["sources"][0]["attempts"][0]
        assert attempt["status"] == "completed"
        assert [row["status"] for row in attempt["requests"]] == [200, 200, 200]
        assert attempt["requests"][0]["path"] == "/robots.txt"
        assert attempt["requests"][-1]["path"].endswith("radio-test")
    engine.dispose()
