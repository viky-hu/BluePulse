from datetime import UTC, datetime, timedelta
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app
from bluepulse_backend.cli import sync_taxonomy
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.editorial import analyze, apply_analysis
from bluepulse_backend.live_model import LiveAnalyzer, ProviderRejected
from bluepulse_backend.models import Material, Source, Topic
from test_editorial_steps import classification_step


def test_other_taxonomy_is_idempotent_and_news_can_be_read_and_filtered(tmp_path):
    address = f"sqlite:///{(tmp_path / 'other.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    sync_taxonomy(address)
    sync_taxonomy(address)
    now = datetime.now(UTC) - timedelta(minutes=1)
    with Session(engine, expire_on_commit=False) as session:
        other = session.scalars(select(Topic).where(Topic.slug == "other")).all()
        assert len(other) == 1 and other[0].enabled and other[0].name_zh == "其它"
        source = Source(slug="other-fixture", name="Test source", excerpt_allowed=True, full_text_allowed=True,
                        selection_threshold=60, allowed_hosts=["example.test"], region="foreign")
        item = Material(source=source, source_title="Concrete technology clue",
                        source_body="Police technology evidence. " * 20,
                        source_url="https://example.test/other", canonical_url="https://example.test/other",
                        content_hash="1" * 64, body_status="full_text", language="en",
                        published_at=now, published_sort_at=now, first_seen_at=now, timeline_kind="fresh")
        session.add(item)
        session.flush()
        result = analyze(item, classification_step("other"))
        apply_analysis(session, item, result, now, {})
        item.grouping_status, item.grouping_value, item.selected_at = "complete", True, now
        session.commit()
        item_id = item.id
        assert item.public and item.relevant and item.featured_candidate
    with TestClient(create_app(address)) as client:
        taxonomy = client.get("/api/v1/taxonomy").json()["items"]
        assert next(row for row in taxonomy if row["slug"] == "other")["name_zh"] == "其它"
        articles = client.get("/api/v1/articles", params={"period": "all", "topic": "other"}).json()
        assert [row["id"] for row in articles["items"]] == [item_id]
        assert client.get("/api/v1/articles", params={"period": "all", "topic": "practice"}).json()["items"] == []
        assert client.get(f"/api/v1/articles/{item_id}").json()["topics"] == ["other"]
        timeline = client.get("/api/v1/site/timeline", params={"topic": "other"})
        assert timeline.status_code == 200
        assert item_id in json.dumps(timeline.json())
    engine.dispose()


@pytest.mark.parametrize("topics", [["other"], ["practice", "other"], ["other", "other"], []])
def test_compatibility_analyzer_requires_one_explicit_main_category(topics):
    payload = {"relevant": True, "title_zh": "具体技术线索", "summary_zh": "原文提供了具体技术线索。",
               "topics": topics}

    def respond(request):
        return httpx.Response(200, json={"id": "fixture-other", "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(payload)}}], "usage": {}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        analyzer = LiveAnalyzer(client, "https://provider.example/v1", "fixture-key", "fixture-model")
        item = Material(source=Source(name="Test source"), source_title="Concrete technology clue",
                        source_url="https://example.test/other", source_body="Evidence. " * 40,
                        body_status="full_text")
        if topics == ["other"]:
            result = analyzer.analyze(item)
            assert result.relevant and result.topics == ("other",)
        else:
            with pytest.raises(ProviderRejected, match="provider_invalid_schema"):
                analyzer.analyze(item)
