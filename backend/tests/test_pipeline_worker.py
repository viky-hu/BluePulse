from datetime import UTC, datetime
from email.utils import format_datetime
import json

import httpx
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


def test_worker_collects_analyzes_groups_and_translates_through_receipts(tmp_path):
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
            if "只有明确无关" in prompt:
                answer = {"label": "PASS"}
            elif "五轴" in prompt:
                answer = {"content_type": "industry_event", "sig": 8, "nov": 8, "cred": 8,
                          "reson": 8, "act": 8}
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
        source.excerpt_allowed = source.full_text_allowed = True
        source.selection_threshold = 60
        session.commit()
    worker = Worker(engine, client, presets={"default": credentials}, budget=Budget(10, 30, 30),
                    collect_enabled=True, slugs=["nist-public-safety"], clock=lambda: when)
    worker.tick()
    for _ in range(8):
        if not worker.run_one():
            break
    with Session(engine) as session:
        article = session.scalar(select(Material))
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
