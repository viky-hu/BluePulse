from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine


def test_response_is_replayed_before_charging_shared_budget(tmp_path):
    from bluepulse_backend.receipts import Budget, BudgetWait, PaidGateway

    engine = make_engine(f"sqlite:///{tmp_path / 'receipts.db'}")
    Base.metadata.create_all(engine)
    kwargs = dict(service="autodl", budget=Budget(5, 10, 30, total=1))
    calls = []

    def send():
        calls.append(True)
        return httpx.Response(200, json={"id": "p1", "choices": []})

    first = PaidGateway(engine, run_key="pilot", **kwargs).request("article:1", "score:1", {"prompt": "a"}, send)
    replay = PaidGateway(engine, run_key="pilot", **kwargs).request("article:1", "score:1", {"prompt": "a"}, send)
    assert replay.json() == first.json()
    with pytest.raises(BudgetWait):
        PaidGateway(engine, run_key="pilot", **kwargs).request("article:1", "score:2", {"prompt": "a"}, send)
    assert len(calls) == 1


def test_expired_worker_cannot_complete_reclaimed_job(tmp_path):
    from bluepulse_backend.work_queue import claim, enqueue, finish

    engine = make_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 8, tzinfo=UTC)
    with Session(engine) as session:
        enqueue(session, "collect", "govuk", {"slug": "govuk"}, now)
        session.commit()
    first = claim(engine, now)
    assert claim(engine, now) is None
    later = now + timedelta(minutes=11)
    second = claim(engine, later)
    assert first.id == second.id
    assert first.token != second.token
    assert finish(engine, first, later) is False
    assert finish(engine, second, later) is True


def test_concurrent_attempts_share_one_reserved_call(tmp_path):
    from bluepulse_backend.receipts import Budget, BudgetWait, PaidGateway

    engine = make_engine(f"sqlite:///{tmp_path / 'concurrent.db'}")
    Base.metadata.create_all(engine)
    start, release = Event(), Event()

    def first():
        start.set()
        assert release.wait(5)
        return httpx.Response(200, json={"id": "first"})

    def request(step, send):
        return PaidGateway(engine, service="example.test", budget=Budget(1, 10, 30)).request("a:1", step, {}, send)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(request, "prefilter", first)
        try:
            assert start.wait(5)
            with pytest.raises(BudgetWait, match="request_budget_60"):
                request("structure", lambda: pytest.fail("budget overshoot"))
        finally:
            release.set()
        assert future.result().json()["id"] == "first"


def test_unknown_releases_automatically_only_once_across_restart(tmp_path):
    from bluepulse_backend.receipts import Budget, PaidGateway, ReceiptUnknown, recover_receipts

    engine = make_engine(f"sqlite:///{tmp_path / 'unknown.db'}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 8, tzinfo=UTC)

    def uncertain():
        raise httpx.ReadTimeout("fixture")

    def request():
        return PaidGateway(engine, service="example.test", budget=Budget(10, 30, 30),
                           clock=lambda: now).request("a:1", "group", {}, uncertain)

    with pytest.raises(ReceiptUnknown):
        request()
    now += timedelta(minutes=31)
    recover_receipts(engine, now)
    with pytest.raises(ReceiptUnknown):
        request()
    now += timedelta(minutes=31)
    recover_receipts(engine, now)
    from bluepulse_backend.editorial_models import PaidReceipt
    from sqlalchemy import select
    with Session(engine) as session:
        row = session.scalar(select(PaidReceipt))
        assert row.status == "unknown" and row.latest_attempt == 2 and row.auto_released


def test_new_grouping_query_only_buys_missing_vectors(tmp_path):
    import json
    from bluepulse_backend.model_steps import Steps
    from bluepulse_backend.receipts import Budget

    engine = make_engine(f"sqlite:///{tmp_path / 'vectors.db'}")
    Base.metadata.create_all(engine)
    env = tmp_path / "embed.env"
    env.write_text("base_url=https://embedding.example.test/v1\nkey=example\nllm_id=fixture\n")
    requests = []

    def send(request):
        texts = json.loads(request.content)["input"]
        requests.append(texts)
        return httpx.Response(200, json={"data": [
            {"index": index, "embedding": [len(text), 1]} for index, text in enumerate(texts)
        ]})

    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        args = (engine, client, {"embed": env}, {"embedding": "embed"}, "fixture", Budget(10, 10, 10))
        assert Steps(*args).embeddings(["existing", "older"]) == [[8, 1], [5, 1]]
        assert Steps(*args).embeddings(["another", "existing", "older"]) == [[7, 1], [8, 1], [5, 1]]
    assert len(requests) == 2 and requests[1] == ["another"]
