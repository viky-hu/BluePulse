from datetime import UTC, datetime
import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.editorial_models import WorkItem
from bluepulse_backend.models import Material, Source
from bluepulse_backend.receipts import Budget
from bluepulse_backend.worker import Worker


@pytest.mark.parametrize("change", [None, "withdrawn", "revision", "override"])
def test_summary_backfill_reuses_pilot_receipt_and_rechecks_current_state(tmp_path, change):
    from bluepulse_backend.admin_models import AdminContentOverride
    from bluepulse_backend.summary_backfill import queue_rewrites
    from bluepulse_backend.work_queue import serialized

    now = datetime(2026, 11, 14, tzinfo=UTC)
    engine = make_engine(f"sqlite:///{tmp_path / 'backfill.db'}")
    Base.metadata.create_all(engine)
    env = tmp_path / "model.env"
    env.write_text("base_url=https://model.example.test/v1\nkey=example\nllm_id=fixture\n")
    with serialized(engine) as session:
        source = Source(slug="source", name="Source", excerpt_allowed=True)
        session.add(source)
        session.flush()
        item = Material(source_id=source.id, canonical_url="https://source.test/item",
                        source_url="https://source.test/item", language="en", content_hash="example",
                        source_title="Radio trial", source_body="The police began a radio trial. " * 20,
                        zh_title="电台试点", zh_summary="原导读", body_status="full_text",
                        relevant=True, public=True, importance_score=63, editorial_revision=1)
        session.add(item)
        session.flush()
        item_id = item.id
        queue_rewrites(session, [item], now, preview=True, max_attempts=1)
    calls = []

    def respond(request):
        calls.append(request)
        if change:
            with serialized(engine) as session:
                item = session.get(Material, item_id)
                if change == "override":
                    session.add(AdminContentOverride(material_id=item_id, fields={"zh_summary": "人工导读"}))
                    item.zh_summary = "人工导读"
                elif change == "withdrawn":
                    item.withdrawn = True
                else:
                    item.revision += 1
        return httpx.Response(200, json={"id": "answer", "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"summaryZh": "警方启动了电台试点。"}, ensure_ascii=False),
        }}]})

    worker = Worker(engine, lambda: httpx.Client(transport=httpx.MockTransport(respond)),
                    presets={"default": env}, budget=Budget(10, 10, 10), clock=lambda: now)
    assert not worker.run_one(kinds={"rewrite_summary"})
    assert worker.run_one(kinds={"rewrite_summary"}, preview=True)
    with serialized(engine) as session:
        item = session.get(Material, item_id)
        job = session.scalar(select(WorkItem))
        assert item.zh_summary == ("人工导读" if change == "override" else "原导读")
        if change:
            assert job.result["skipped"] == {"withdrawn": "not_public", "revision": "superseded",
                                             "override": "manual_summary"}[change]
        else:
            assert job.result["summary"] == "警方启动了电台试点。"
            queue_rewrites(session, [item], now, preview=False, max_attempts=1)
    if change is None:
        assert not worker.run_one(kinds={"rewrite_summary"}, preview=True)
        assert worker.run_one(kinds={"rewrite_summary"}, preview=False)
        with Session(engine) as session:
            item = session.get(Material, item_id)
            assert item.zh_summary == "警方启动了电台试点。"
            assert (item.zh_title, item.importance_score, item.editorial_revision) == ("电台试点", 63, 1)
            assert len(session.scalars(select(WorkItem)).all()) == 1
    assert len(calls) == 1


def test_reviewed_copy_can_recover_an_unknown_request_without_sending_again(tmp_path):
    from bluepulse_backend.editorial import input_hash, rewrite_input
    from bluepulse_backend.editorial_copy import COPY_VERSION
    from bluepulse_backend.editorial_models import PaidReceipt
    from bluepulse_backend.summary_backfill import _apply_review, queue_rewrites
    from bluepulse_backend.work_queue import serialized

    now = datetime(2026, 11, 14, tzinfo=UTC)
    engine = make_engine(f"sqlite:///{tmp_path / 'review.db'}")
    Base.metadata.create_all(engine)
    env = tmp_path / "model.env"
    env.write_text("base_url=https://model.example.test/v1\nkey=example\nllm_id=fixture\n")
    with serialized(engine) as session:
        source = Source(slug="source", name="Source", excerpt_allowed=True)
        session.add(source)
        session.flush()
        item = Material(source_id=source.id, canonical_url="https://source.test/item",
                        source_url="https://source.test/item", language="en", content_hash="example",
                        source_title="Radio trial", source_body="The police began a radio trial. " * 20,
                        zh_summary="原导读", body_status="full_text", relevant=True, public=True,
                        editorial_revision=1)
        session.add(item)
        session.flush()
        item_id = item.id
        queue_rewrites(session, [item], now, preview=False, max_attempts=1)

    def timeout(request):
        raise httpx.ReadTimeout("outcome unknown", request=request)

    worker = Worker(engine, lambda: httpx.Client(transport=httpx.MockTransport(timeout)),
                    presets={"default": env}, budget=Budget(10, 10, 10), clock=lambda: now)
    assert worker.run_one(kinds={"rewrite_summary"}, preview=False)
    with serialized(engine) as session:
        item = session.get(Material, item_id)
        data = rewrite_input(item)
        review = tmp_path / "review.json"
        review.write_text(json.dumps({"version": COPY_VERSION, "items": [{
            "id": item_id, "summary": "警方启动了电台试点。",
            "input_hash": input_hash(json.dumps(data, ensure_ascii=False, sort_keys=True)),
        }]}))
        _apply_review(session, review, now)
        queue_rewrites(session, [item], now, preview=False, max_attempts=1)
    assert worker.run_one(kinds={"rewrite_summary"}, preview=False)
    with Session(engine) as session:
        assert session.get(Material, item_id).zh_summary == "警方启动了电台试点。"
        assert session.scalar(select(PaidReceipt)).status == "unknown"
