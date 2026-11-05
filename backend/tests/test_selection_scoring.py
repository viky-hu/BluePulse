from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.live_model import LiveAnalyzer, ProviderRejected, SCORE_PROMPT
from bluepulse_backend.model_processing import process_model_batch
from bluepulse_backend.models import AnalysisAttempt, Material, Source
from bluepulse_backend.pipeline import (
    AnalysisResult, Candidate, MockAnalyzer, MockSourceAdapter, UnknownOutcome,
    ingest, process_pending,
)
from bluepulse_backend.selection_scoring import SelectionScore, WEIGHTS, process_selection


def setup_material(tmp_path, threshold=60):
    engine = make_engine(f"sqlite:///{(tmp_path / 'scores.db').as_posix()}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    source = Source(slug="nist", name="NIST", region="foreign", country_code="US",
                    language="en", source_type="official", topics=[],
                    allowed_hosts=["www.nist.gov"], excerpt_allowed=True,
                    selection_threshold=threshold)
    session.add(source)
    session.commit()
    url = "https://www.nist.gov/news-events/news/score-fixture"
    candidate = Candidate(url=url, title="First responder radio interoperability",
                          body="The trial documented radio interoperability and constraints. " * 10,
                          published_at=datetime(2026, 11, 3, tzinfo=UTC), language="en")
    ingest(session, source, MockSourceAdapter([candidate]))
    material = session.scalar(select(Material))
    answer = AnalysisResult(relevant=True, title_zh="通信互通试验", summary_zh="原文记录通信互通试验。",
                            topics=("practice",), importance_score=0,
                            provider_meta={"scoring_required": True})
    process_pending(session, MockAnalyzer({url: answer}))
    return engine, session, material, answer


class SequenceScorer:
    selection_input_version = "five-axis-v1"

    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def score(self, material):
        self.calls += 1
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


def score(value: int, request_id: str) -> SelectionScore:
    return SelectionScore("model_release", value, value, value, value, value,
                          provider_meta={"request_id": request_id})


def test_all_seven_weight_rows_are_valid_and_axes_are_strict():
    assert len(WEIGHTS) == 7
    assert all(sum(weights) == 10 for weights in WEIGHTS.values())
    assert all(f"{kind}={'/'.join(map(str, weights))}" in SCORE_PROMPT
               for kind, weights in WEIGHTS.items())
    assert score(7, "a").attention_score == 70
    with pytest.raises(ValueError, match="invalid_selection_score"):
        SelectionScore("model_release", True, 5, 5, 5, 5).attention_score
    with pytest.raises(ValueError, match="invalid_selection_score"):
        score(11, "a").attention_score


def test_two_independent_receipts_and_sum_threshold(tmp_path):
    engine, session, material, _ = setup_material(tmp_path, threshold=60)
    scorer = SequenceScorer([score(5, "request-one"), score(7, "request-two")])
    result = process_selection(session, material, scorer, max_calls=2)
    assert result == {"status": "complete", "calls_started": 2, "scores": [50, 70],
                      "average": 60, "threshold": 60, "candidate": True}
    assert material.importance_score == 60 and material.featured_candidate
    attempts = session.scalars(select(AnalysisAttempt).where(
        AnalysisAttempt.input_version.like("five-axis-v1-r%"))).all()
    assert {row.input_version for row in attempts} == {"five-axis-v1-r1", "five-axis-v1-r2"}
    assert all(row.status == "applied" for row in attempts)
    assert all(row.result["sig"] in {5, 7} for row in attempts)
    assert process_selection(session, material, scorer, max_calls=0)["calls_started"] == 0
    assert scorer.calls == 2
    session.close()
    engine.dispose()


def test_partial_budget_resumes_second_round_without_repaying_first(tmp_path):
    engine, session, material, _ = setup_material(tmp_path, threshold=65)
    scorer = SequenceScorer([score(6, "one"), score(7, "two")])
    first = process_selection(session, material, scorer, max_calls=1)
    assert first["status"] == "partial" and first["calls_started"] == 1
    assert not material.featured_candidate and material.importance_score == 0
    second = process_selection(session, material, scorer, max_calls=1)
    assert second["status"] == "complete" and second["calls_started"] == 1
    assert second["scores"] == [60, 70] and second["average"] == 65
    assert material.featured_candidate and scorer.calls == 2
    session.close()
    engine.dispose()


def test_unknown_second_call_does_not_retry_or_create_candidate(tmp_path):
    engine, session, material, _ = setup_material(tmp_path)
    scorer = SequenceScorer([score(8, "one"), UnknownOutcome("provider_timeout_unknown")])
    first = process_selection(session, material, scorer, max_calls=2)
    assert first["status"] == "unknown" and first["calls_started"] == 2
    again = process_selection(session, material, scorer, max_calls=2)
    assert again["status"] == "unknown" and again["calls_started"] == 0
    assert scorer.calls == 2 and material.public and not material.featured_candidate
    session.close()
    engine.dispose()


def test_uncalibrated_threshold_and_duplicate_response_fail_closed(tmp_path):
    engine, session, material, _ = setup_material(tmp_path, threshold=None)
    scorer = SequenceScorer([score(9, "one"), score(9, "two")])
    result = process_selection(session, material, scorer, max_calls=2)
    assert result["status"] == "uncalibrated" and result["average"] == 90
    assert not material.featured_candidate
    material.source.selection_threshold = 60
    session.commit()
    assert process_selection(session, material, scorer, max_calls=0)["candidate"]
    session.close()
    engine.dispose()

    engine, session, material, _ = setup_material(tmp_path / "other", threshold=60)
    same_id = SequenceScorer([score(9, "same"), score(9, "same")])
    result = process_selection(session, material, same_id, max_calls=2)
    assert result["status"] == "duplicate_response" and not material.featured_candidate
    session.close()
    engine.dispose()


def test_model_batch_caps_total_classification_and_score_calls(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'batch.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(slug="nist", name="NIST", region="foreign", country_code="US",
                        language="en", source_type="official", topics=[],
                        allowed_hosts=["www.nist.gov"], excerpt_allowed=True,
                        selection_threshold=60)
        session.add(source)
        session.commit()
        url = "https://www.nist.gov/news-events/news/batch"
        ingest(session, source, MockSourceAdapter([Candidate(
            url=url, title="Radio test", body="Radio interoperability test evidence. " * 12)]))

        class Combined(SequenceScorer):
            input_version = "analysis-five-axis-v1"

            def analyze(self, material):
                return AnalysisResult(True, "通信试验", "原文描述通信试验。", ("practice",), 0,
                                      provider_meta={"scoring_required": True})

        analyzer = Combined([score(7, "one"), score(8, "two")])
        first = process_model_batch(session, analyzer, source_id=source.id, max_calls=2)
        assert first["calls_used"] == 2 and first["score_calls"] == 1
        assert session.scalar(select(Material)).selection_status == "partial"
        second = process_model_batch(session, analyzer, source_id=source.id, max_calls=1)
        assert second["calls_used"] == 1 and second["score_calls"] == 1
        assert session.scalar(select(Material)).featured_candidate
        assert analyzer.calls == 2
    engine.dispose()


def test_live_score_request_contains_same_material_not_source_threshold(tmp_path):
    engine, session, material, _ = setup_material(tmp_path, threshold=76)
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        index = len(requests)
        return httpx.Response(200, json={"id": f"request-{index}", "model": "fixture-model",
                                         "usage": {"prompt_tokens": 20, "completion_tokens": 8},
                                         "choices": [{"message": {"content": json.dumps({
                                             "content_type": "research_paper", "sig": 7, "nov": 6,
                                             "cred": 5, "reson": 4, "act": 3})}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        scorer = LiveAnalyzer(client, "https://model.example/v1", "fixture-secret", "fixture-model")
        result = process_selection(session, material, scorer, max_calls=2)
    assert result["scores"] == [61, 61] and result["average"] == 61
    assert result["candidate"] is False
    assert len(requests) == 2
    assert requests[0]["messages"] == requests[1]["messages"]
    attempts = session.scalars(select(AnalysisAttempt).where(
        AnalysisAttempt.input_version.like("axis-%"))).all()
    assert len(attempts) == 2
    assert all(row.result["raw_response"]["content"] for row in attempts)
    assert all(row.result["provider_meta"]["input_truncated"] is False for row in attempts)
    user_data = json.loads(requests[0]["messages"][1]["content"])
    assert set(user_data) == {"title", "text"}
    assert "fixture-secret" not in json.dumps(requests)
    session.close()
    engine.dispose()


def test_revision_requires_fresh_two_score_receipts(tmp_path):
    engine, session, material, answer = setup_material(tmp_path, threshold=60)
    first = SequenceScorer([score(8, "old-one"), score(8, "old-two")])
    assert process_selection(session, material, first, max_calls=2)["candidate"]
    source = material.source
    changed = Candidate(url=material.source_url, title=material.source_title,
                        body="A corrected technical result with new limitations. " * 12,
                        published_at=datetime(2026, 11, 3, tzinfo=UTC), language="en")
    ingest(session, source, MockSourceAdapter([changed]))
    session.refresh(material)
    assert material.revision == 2 and not material.featured_candidate
    assert material.selection_status == "pending"
    process_pending(session, MockAnalyzer({material.canonical_url: answer}))
    second = SequenceScorer([score(5, "new-one"), score(5, "new-two")])
    result = process_selection(session, material, second, max_calls=2)
    assert result["scores"] == [50, 50] and not result["candidate"]
    assert len(session.scalars(select(AnalysisAttempt).where(
        AnalysisAttempt.input_version.like("five-axis-v1-r%"))).all()) == 4
    session.close()
    engine.dispose()


def test_live_score_rejects_invalid_axis():
    def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "content_type": "model_release", "sig": True, "nov": 5, "cred": 5,
            "reson": 5, "act": 5})}}]})

    material = Material(source_title="Test", source_body="A" * 400)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderRejected, match="provider_invalid_schema"):
            LiveAnalyzer(client, "https://model.example/v1", "fixture-key", "fixture-model").score(material)
