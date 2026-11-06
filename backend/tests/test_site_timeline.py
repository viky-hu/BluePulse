from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.models import FeaturedEdition, FeaturedSlot, Material, Source, Topic
from bluepulse_backend.pipeline import AnalysisResult, Candidate, MockAnalyzer, MockSourceAdapter, ingest, process_pending


def test_timeline_lists_only_current_visible_materials_and_paginates(tmp_path):
    address = f"sqlite:///{(tmp_path / 'timeline.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        source = Source(slug="sample", name="Official sample", region="foreign", country_code="US",
                        language="en", source_type="official", topics=[],
                        allowed_hosts=["example.test"], excerpt_allowed=True)
        session.add_all([source, Topic(slug="paper", name_zh="研究", name_en="Paper")])
        session.commit()
        candidates = [
            Candidate(url="https://example.test/one", title="Technology research one",
                      body="First complete original body. " * 30,
                      published_at=now - timedelta(hours=2)),
            Candidate(url="https://example.test/two", title="Technology research two",
                      body="Second complete original body. " * 30,
                      published_date=now.date()),
            Candidate(url="https://example.test/old", title="Old technology research",
                      body="Older complete original body. " * 30,
                      published_at=now - timedelta(days=70)),
        ]
        ingest(session, source, MockSourceAdapter(candidates))
        answers = {item.url: AnalysisResult(relevant=True, title_zh=None, summary_zh="内部摘要",
                                            topics=("paper",), importance_score=50)
                   for item in candidates}
        assert process_pending(session, MockAnalyzer(answers))["applied"] == 3
        edition = FeaturedEdition(window_policy="auto_recent_7d")
        session.add(edition)
        session.flush()
        recent = session.scalars(select(Material).where(Material.source_id == source.id,
            Material.timeline_kind == "fresh").order_by(Material.source_url)).all()
        for index, article in enumerate(recent):
            session.add(FeaturedSlot(edition_id=edition.id, article_id=article.id,
                slot=f"p{index}", importance_score=0,
                featured_reason="近期自动编排；未进行五轴评分"))
        session.commit()
    with TestClient(create_app(address)) as client:
        first = client.get("/api/v1/site/timeline", params={"region": "foreign", "topic": "paper", "limit": 1})
        assert first.status_code == 200
        data = first.json()
        assert data["filters"] == {"region": "foreign", "topic": "paper"}
        assert len(data["cards"]) == 1 and data["nextCursor"]
        assert data["hot"] is None
        assert data["cards"][0]["item"]["selected"] is True
        assert data["cards"][0]["group"] is None
        assert sum(data["dayCounts"].values()) == 2  # Full filtered group count, not this page.
        second = client.get("/api/v1/site/timeline", params={
            "region": "foreign", "topic": "paper", "limit": 1, "cursor": data["nextCursor"]})
        assert second.status_code == 200 and len(second.json()["cards"]) == 1
        assert second.json()["cards"][0]["key"] != data["cards"][0]["key"]
        assert second.json()["nextCursor"] is None
        assert client.get("/api/v1/site/timeline", params={"region": "domestic"}).json()["cards"] == []
        assert client.get("/api/v1/site/timeline", params={"topic": "law"}).json()["cards"] == []
        assert client.get("/api/v1/site/timeline", params={"cursor": data["nextCursor"]}).status_code == 400
    engine.dispose()
