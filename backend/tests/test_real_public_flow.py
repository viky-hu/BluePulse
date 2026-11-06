from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app
from bluepulse_backend.classify_sources import classify_once_per_source
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.models import Source
from bluepulse_backend.pipeline import AnalysisResult, Candidate, MockAnalyzer, MockSourceAdapter, ingest
from bluepulse_backend.source_collection import SOURCES
from bluepulse_backend.source_permissions import (
    allow_excerpts_for_active_sources, allow_full_text_for_active_sources,
)


def test_all_source_excerpt_decision_and_classification_only_public_flow(tmp_path):
    address = f"sqlite:///{(tmp_path / 'real-public.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    relevant_slug, irrelevant_slug = "govuk", "ccgp-policing-tech"
    answers = {}
    with Session(engine) as session:
        permission = allow_excerpts_for_active_sources(session)
        assert permission["active_sources"] == 15
        assert len(permission["excerpt_enabled"]) == 15
        assert all(source.excerpt_allowed and not source.full_text_allowed
                   for source in session.scalars(select(Source)).all())
        for slug, relevant in ((relevant_slug, True), (irrelevant_slug, False)):
            spec = SOURCES[slug]
            source = session.scalar(select(Source).where(Source.slug == slug))
            url = f"https://{spec.host}/real-public-flow-test"
            ingest(session, source, MockSourceAdapter([Candidate(
                url=url, title=f"{slug} report", body="Detailed public safety evidence. " * 16)]))
            answers[url] = AnalysisResult(
                relevant, f"{slug} 中文标题" if relevant else None,
                "原文记载了警务技术实践。" if relevant else None,
                ("practice",) if relevant else (), 0)
        report = classify_once_per_source(session, MockAnalyzer(answers), max_calls=2)
        assert report["calls_used"] == 2
        assert next(row for row in report["sources"] if row["source"] == relevant_slug)["public"] == 1
        assert next(row for row in report["sources"] if row["source"] == irrelevant_slug)["public"] == 0
    with TestClient(create_app(address)) as client:
        items = client.get("/api/v1/articles?period=all").json()["items"]
        assert len(items) == 1
        detail = client.get(f"/api/v1/articles/{items[0]['id']}")
        assert detail.status_code == 200
        assert detail.json()["source_body"] is None
        assert detail.json()["summary"] == "原文记载了警务技术实践。"
    with Session(engine) as session:
        permission = allow_full_text_for_active_sources(session)
        assert len(permission["full_text_enabled"]) == 15
        assert permission["excerpt_enabled"] == []
    with TestClient(create_app(address)) as client:
        detail = client.get(f"/api/v1/articles/{items[0]['id']}")
        assert detail.status_code == 200
        assert "Police radio" not in (detail.json()["source_body"] or "")
        assert "Detailed public safety evidence" in detail.json()["source_body"]
    engine.dispose()
