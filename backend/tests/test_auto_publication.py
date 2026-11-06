from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend import auto_publication
from bluepulse_backend.api import create_app
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.fact_grouping import create_recent_featured, group_public_materials
from bluepulse_backend.material_identity import title_key
from bluepulse_backend.models import AutoPublicationJob, FactGroup, FactReport, Material, Source


def _article(session: Session, source: Source, title: str, suffix: str, when: datetime) -> Material:
    article = Material(
        canonical_url=f"https://www.nist.gov/news-events/news/{suffix}",
        source_url=f"https://www.nist.gov/news-events/news/{suffix}",
        source_id=source.id, source_title=title, title_key=title_key(title),
        source_body=(suffix + " documented police radio evidence. ") * 15,
        language="en", published_at=when, published_sort_at=when,
        first_seen_at=when + timedelta(minutes=5), fetched_at=when + timedelta(minutes=5),
        revision=1, content_hash=suffix.ljust(64, "0"), state="publication_pool",
        timeline_kind="fresh", body_status="full_text", translation_status="not_required",
        zh_summary="原文描述警务通信实践。", importance_score=0, topics=["practice"],
        relevant=True, featured_candidate=False, grouping_status="pending",
        public=True, withdrawn=False,
    )
    session.add(article)
    return article


def test_conservative_fact_grouping_unscored_featured_and_internal_job(tmp_path, monkeypatch):
    address = f"sqlite:///{(tmp_path / 'automatic.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    when = datetime.now(UTC) - timedelta(hours=2)
    with Session(engine) as session:
        sources = []
        for index in range(3):
            source = Source(slug=f"source-{index}", name=f"Source {index}", region="foreign",
                            country_code="US", language="en", source_type="official",
                            topics=[], allowed_hosts=["www.nist.gov"],
                            excerpt_allowed=True, full_text_allowed=True)
            session.add(source)
            sources.append(source)
        session.flush()
        a = _article(session, sources[0], "Police radio deployment result", "alpha", when)
        b = _article(session, sources[1], "Police radio deployment result", "beta", when)
        c = _article(session, sources[2], "Separate forensic device launch", "gamma", when)
        session.commit()
        grouped = group_public_materials(session)
        assert grouped["groups_created"] == 2 and grouped["members_assigned"] == 3
        fact = session.get(FactReport, a.id).fact_id
        assert session.get(FactReport, b.id).fact_id == fact
        assert session.get(FactReport, c.id).fact_id != fact
        assert session.scalar(select(FactGroup).where(FactGroup.id == fact)) is not None
        edition = create_recent_featured(session)
        assert edition["created"] and edition["selected"] == 2
        assert create_recent_featured(session)["created"] is False
        assert not any(row.featured_candidate for row in (a, b, c))

    with TestClient(create_app(address)) as client:
        featured = client.get("/api/v1/home/featured")
        assert featured.status_code == 200 and len(featured.json()["items"]) == 2
        assert all("未进行五轴评分" in item["featured_reason"] for item in featured.json()["items"])
        timeline = client.get("/api/v1/site/timeline")
        assert timeline.status_code == 200 and len(timeline.json()["cards"]) == 2
        card = next(item for item in timeline.json()["cards"] if item["group"])
        assert card["group"]["reportCount"] == 2
        reports = client.get(f"/api/v1/site/groups/{fact}/reports")
        assert reports.status_code == 200 and len(reports.json()["reports"]) == 2
        assert client.post("/api/v1/internal/auto-publication/jobs", json={
            "idempotency_key": "run-one", "source_slugs": ["govuk"]}).status_code == 503
        monkeypatch.setenv("BLUEPULSE_INTERNAL_TOKEN", "test-internal-token")
        headers = {"X-Bluepulse-Worker-Token": "test-internal-token"}
        assert client.post("/api/v1/internal/auto-publication/jobs", headers={
            "X-Bluepulse-Worker-Token": "wrong"}, json={
            "idempotency_key": "run-one", "source_slugs": ["govuk"]}).status_code == 403
        body = {"idempotency_key": "run-one", "source_slugs": ["govuk"]}
        queued = client.post("/api/v1/internal/auto-publication/jobs", headers=headers, json=body)
        assert queued.status_code == 202 and queued.json()["status"] == "pending"
        assert client.post("/api/v1/internal/auto-publication/jobs", headers=headers,
                           json=body).json()["id"] == queued.json()["id"]
        assert client.post("/api/v1/internal/auto-publication/jobs", headers=headers, json={
            **body, "max_items": 1}).status_code == 409
        assert client.get(f"/api/v1/internal/auto-publication/jobs/{queued.json()['id']}",
                          headers=headers).status_code == 200

    monkeypatch.setattr(auto_publication, "run_cycle", lambda *_args, **_kwargs: {
        "sources": [], "model_used": 0})
    with Session(engine) as session:
        job_id = auto_publication.claim_next_job(session)
        assert job_id == queued.json()["id"]
        result = auto_publication.run_claimed_job(session, job_id, lambda: None)
        assert result["featured"]["selected"] == 2
        assert session.get(AutoPublicationJob, job_id).status == "completed"
        assert auto_publication.claim_next_job(session) is None
    engine.dispose()
