from datetime import UTC, datetime
from email.utils import format_datetime
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.editorial_models import PaidAttempt, Story, WorkItem
from bluepulse_backend.models import Material, Source
from bluepulse_backend.publication import selected
from bluepulse_backend.receipts import Budget
from bluepulse_backend.source_collection import SOURCES, ensure_source


def test_exhausted_bounded_batch_leaves_article_available_to_normal_worker(tmp_path):
    from bluepulse_backend.worker import _schedule_material

    engine = make_engine(f"sqlite:///{tmp_path / 'run-budget.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        source = ensure_source(session, SOURCES["nist-public-safety"])
        item = Material(source=source, canonical_url="https://www.nist.gov/test",
                        source_url="https://www.nist.gov/test", source_title="Test", content_hash="x",
                        language="en")
        session.add(item)
        session.flush()
        _schedule_material(session, item, now, run_key="bounded")
        _schedule_material(session, item, now)
        assert len(session.scalars(select(WorkItem)).all()) == 1
        bounded = session.scalar(select(WorkItem))
        bounded.status, bounded.error = "failed", "request_budget_total"
        session.flush()
        _schedule_material(session, item, now)
        jobs = session.scalars(select(WorkItem).order_by(WorkItem.identity.desc())).all()
        assert [job.status for job in jobs] == ["failed", "pending"]
        assert [job.payload["run_key"] for job in jobs] == ["bounded", None]


@pytest.mark.parametrize("decision", ["unknown", "unsupported", "potential-low", "potential-excerpt", "direct-high"])
def test_worker_collects_analyzes_groups_and_translates_through_receipts(tmp_path, decision):
    from bluepulse_backend.admin_operations import admin_rerun
    from bluepulse_backend.api import create_app
    from bluepulse_backend.fact_grouping import create_confirmed_featured
    from bluepulse_backend.worker import Worker

    engine = make_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    when = datetime.now(UTC)
    credentials = tmp_path / "fake.env"
    credentials.write_text("base_url=https://models.example.test/v1\nkey=fixture-key\nllm_id=fixture\n")
    body = "The city police started a documented radio interoperability trial. " * 15
    detail = "https://www.nist.gov/news-events/news/police-radio-trial"
    rss = (f"<rss><channel><item><title>Police radio trial</title><link>{detail}</link>"
           f"<pubDate>{format_datetime(when)}</pubDate></item></channel></rss>")
    requests = []

    def transport(request):
        if request.url.host == "models.example.test":
            messages = json.loads(request.content)["messages"]
            prompt, inputs = messages[0]["content"], json.loads(messages[1]["content"])
            requests.append(prompt)
            if "{label,relevance,reason,evidence}" in prompt:
                answer = {"label": "PASS", "relevance": "direct", "reason": "测试警务电台互通",
                          "evidence": "The city police started a documented radio interoperability trial."}
                if decision == "unknown":
                    answer = {"label": "UNKNOWN", "reason": "材料不足"}
                elif decision == "unsupported":
                    answer = {"label": "PASS", "reason": "采购方为警队"}
                elif decision in ("potential-low", "potential-excerpt"):
                    answer["relevance"] = "potential"
            elif "五轴" in prompt:
                grade = 3 if decision.startswith("potential-") else 8
                answer = {"content_type": "industry_event", **dict.fromkeys(("sig", "nov", "cred", "reson", "act"), grade)}
            elif "scope" in prompt:
                answer = {"scope": "single", "category": "practice", "tags": ["radio"],
                          "fact": {"title": "警务电台试点", "evidence": "started a documented radio interoperability trial"}}
            elif "blocks" in inputs:
                answer = {"blocks": ["市警察启动了一项有记录的无线电互操作性试验。"]}
            else:
                answer = {"titleZh": "警务电台试点", "summaryZh": "市警察启动了互通试验。"}
            return httpx.Response(200, json={"id": str(len(requests)), "choices": [
                {"message": {"content": json.dumps(answer, ensure_ascii=False)}, "finish_reason": "stop"}]})
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:")
        if request.url.path.endswith("rss.xml"):
            return httpx.Response(200, text=rss)
        return httpx.Response(200, text=f'<article><div class="text-with-summary"><p>{body}</p></div></article>')

    def client():
        return httpx.Client(transport=httpx.MockTransport(transport))

    with Session(engine) as session:
        source = ensure_source(session, SOURCES["nist-public-safety"])
        source.excerpt_allowed = True
        source.full_text_allowed = decision != "potential-excerpt"
        source.selection_threshold = 60
        session.commit()
    worker = Worker(engine, client, presets={"default": credentials}, budget=Budget(10, 30, 30),
                    collect_enabled=True, slugs=["nist-public-safety"], clock=lambda: when,
                    translation_enabled=decision != "potential-low")
    worker.tick()
    for _ in range(8):
        if not worker.run_one():
            break
    if decision == "potential-low":
        assert len(requests) == 5 and not worker.run_one(kinds={"translate"})
        with Session(engine) as session:
            queued = session.scalar(select(WorkItem).where(WorkItem.kind == "translate"))
            assert queued.status == "pending" and queued.attempts == 0
        worker.translation_enabled = True
        assert worker.run_one(kinds={"translate"})
    if decision == "unknown":
        from bluepulse_backend.relevance_recheck import batch

        with Session(engine) as session:
            article = session.scalar(select(Material))
            article.editorial_data = {"label": "PASS"}
            article.public = article.relevant = True
            article.zh_summary = "一篇留待复判的历史稿件。"
            session.commit()
            assert batch(session, when, limit=1, reason="验证复判")["queued"] == 1
            session.commit()
        assert worker.run_one(kinds={"analyze"})
        assert worker.run_one(kinds={"group"})
        with Session(engine) as session:
            assert batch(session, when, limit=1)["outcomes"] == {"hidden": 1}
    with Session(engine) as session:
        article = session.scalar(select(Material))
        if decision != "direct-high":
            expected = decision.startswith("potential-")
            translated = decision == "potential-low"
            assert article.public is expected
            assert not selected(article, at=when)
            assert len(requests) == (6 if translated else 5 if expected else 1)
            with TestClient(create_app(str(engine.url))) as client:
                detail = client.get(f"/api/v1/articles/{article.id}")
                assert detail.status_code == (200 if expected else 404)
                if expected:
                    reader = detail.json()["reader"]
                    assert reader["hasTranslation"] is translated
                    if translated:
                        assert reader["bodyLanguage"] == "zh" and reader["body"]["complete"]
                        original = client.get(f"/api/v1/articles/{article.id}?body_language=original").json()["reader"]
                        assert original["bodyLanguage"] == "original"
                    else:
                        assert reader["body"] is None
                items = client.get("/api/v1/articles?period=all").json()["items"]
                assert [item["id"] for item in items] == ([article.id] if expected else [])
                assert client.get("/api/v1/home/featured").json()["items"] == []
            return
        assert article and selected(article, at=when)
        assert article.zh_body and article.translation_revision == article.revision
        assert article.translation_status == "available"
        assert session.scalar(select(Story)).title == "警务电台试点"
        assert len(session.scalars(select(PaidAttempt)).all()) == len(requests) == 6
        article_id = article.id
        story_id = session.scalar(select(Story.id))

    with Session(engine) as session:
        assert create_confirmed_featured(session, now=when)["selected"] == 1
    with TestClient(create_app(str(engine.url))) as client:
        assert client.get("/api/v1/site/timeline").json()["cards"][0]["item"]["id"] == article_id
        assert client.get("/api/v1/home/featured").json()["items"][0]["article"]["id"] == article_id
        reader = client.get(f"/api/v1/articles/{article_id}").json()["reader"]
        assert reader["hasTranslation"] and reader["body"]["complete"]
        assert client.get(f"/api/v1/site/stories/{story_id}").json()["publicId"] == story_id
        with Session(engine) as session:
            article = session.get(Material, article_id)
            article.withdrawn = True
            session.commit()
        assert client.get(f"/api/v1/articles/{article_id}").status_code == 404
        assert client.get("/api/v1/site/timeline").json()["cards"] == []
        assert client.get("/api/v1/home/featured").json()["items"] == []
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PaidAttempt)) == 6
        article = session.get(Material, article_id)
        article.withdrawn = False
        next_revision = article.revision + 1
        article.revision = article.editorial_revision = next_revision
        article.source_body += " New evidence for the revised article."
        # The saved status can outlive the translation revision in older rows.
        session.commit()
    worker.tick()
    assert worker.run_one(kinds={"translate"})
    with Session(engine) as session:
        article = session.get(Material, article_id)
        assert article.translation_revision == next_revision
        assert session.scalar(select(func.count()).select_from(PaidAttempt)) == 7
        admin_rerun(session, article, "translate", explicit=True)
        session.commit()
    worker.clock = lambda: datetime.now(UTC)
    assert worker.run_one(kinds={"translate"})
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PaidAttempt)) == 8
