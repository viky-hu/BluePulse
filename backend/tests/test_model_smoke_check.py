from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import make_engine
from bluepulse_backend.models import AnalysisAttempt, Material


def configuration(tmp_path):
    path = tmp_path / "test.env"
    path.write_text("base_url=https://www.autodl.art/api/v1\nkey=fixture-secret\n"
                    "llm_id=DeepSeek-V4.1-Flash-1017\n", encoding="utf-8")
    return path


def provider(output_dir, *, failure=None):
    sent = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "DeepSeek-V4.1-Flash-1017"}]})
        manifest = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
        assert manifest["paid_calls_started"] == len(sent) + 1
        assert manifest["calls"][-1]["status"] == "started"
        sent.append(json.loads(request.content))
        if failure == "timeout":
            raise httpx.ReadTimeout("fixture-secret", request=request)
        if failure == "http":
            return httpx.Response(400, json={"error": {"message": "fixture-secret"}})
        if len(sent) == 1:
            answer = {"relevant": True, "title_zh": "测试：搜救训练计划",
                      "summary_zh": "这是一条虚构测试材料，描述计划中的警务无人机搜救训练。", "topics": ["practice"]}
        else:
            answer = {"content_type": "product_launch", "sig": 4, "nov": 3,
                      "cred": 2, "reson": 4, "act": 3}
        if failure == "invalid":
            answer = {}
        reasoning = "private reasoning must never be saved" if failure == "thinking" else ""
        return httpx.Response(200, json={"id": f"fixture-{len(sent)}", "usage": {
            "prompt_tokens": 40, "completion_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 1 if reasoning else 0}},
            "choices": [{"finish_reason": "echo-fixture-secret" if failure == "thinking" else "stop", "message": {
                "content": json.dumps(answer), "reasoning_content": reasoning}}]})
    return sent, httpx.MockTransport(handler)


def test_smoke_is_off_by_default_without_reading_credentials_or_opening_database(tmp_path):
    from bluepulse_backend.model_smoke_check import run
    output = tmp_path / "disabled"
    result = run(output, env=tmp_path / "missing.env")
    assert result["status"] == "disabled" and result["paid_calls_started"] == 0
    assert not output.exists()


def test_transient_windows_receipt_lock_retries_disk_only(tmp_path, monkeypatch):
    from bluepulse_backend.model_smoke_check import run
    original = Path.replace
    failures = []
    def temporarily_locked(path, target):
        if path.name == "report.tmp" and len(failures) < 2:
            failures.append(path)
            raise PermissionError("transient file lock")
        return original(path, target)
    monkeypatch.setattr(Path, "replace", temporarily_locked)
    output = tmp_path / "windows-lock"
    sent, transport = provider(output)
    report = run(output, env=configuration(tmp_path), execute=True, allow_paid_model=True,
                 max_model_calls_total=3, transport=transport)
    assert report["status"] == "passed" and len(failures) == 2 and len(sent) == 3


def test_three_call_smoke_saves_receipts_before_parsing_and_keeps_fixture_private(tmp_path):
    from bluepulse_backend.model_smoke_check import run
    output = tmp_path / "smoke"
    sent, transport = provider(output)
    report = run(output, env=configuration(tmp_path), execute=True, allow_paid_model=True,
                 max_model_calls_total=3, transport=transport)
    assert report["status"] == "passed" and len(sent) == report["paid_calls_started"] == 3
    assert [call["stage"] for call in report["calls"]] == ["classification", "score-1", "score-2"]
    assert all(call["status"] == "parsed" for call in report["calls"])
    assert all(call["response"]["choices"][0]["message"]["content"] for call in report["calls"])
    assert sent[1]["messages"] == sent[2]["messages"]
    assert all(request["thinking"] == {"type": "disabled"} for request in sent)
    engine = make_engine(report["database_url"])
    with Session(engine) as session:
        row = session.scalar(select(Material))
        assert not row.public and not row.source.excerpt_allowed and not row.source.full_text_allowed
        attempts = session.scalars(select(AnalysisAttempt)).all()
        assert len(attempts) == 3 and all(attempt.status == "applied" for attempt in attempts)
    engine.dispose()
    with pytest.raises(ValueError, match="output_directory_must_be_empty"):
        run(output, env=configuration(tmp_path), execute=True, allow_paid_model=True,
            max_model_calls_total=3, transport=transport)
    assert len(sent) == 3


@pytest.mark.parametrize("failure,expected", [("invalid", "failed"), ("http", "failed"),
    ("timeout", "unknown"), ("thinking", "failed")])
def test_smoke_stops_after_first_failure_without_retries_and_redacts_secrets(tmp_path, failure, expected):
    from bluepulse_backend.model_smoke_check import run
    output = tmp_path / "failed"
    sent, transport = provider(output, failure=failure)
    report = run(output, env=configuration(tmp_path), execute=True, allow_paid_model=True,
                 max_model_calls_total=3, transport=transport)
    assert report["status"] == expected and len(sent) == report["paid_calls_started"] == 1
    persisted = (output / "report.json").read_text(encoding="utf-8")
    assert "fixture-secret" not in persisted
    assert "private reasoning must never be saved" not in persisted
    engine = make_engine(report["database_url"])
    with Session(engine) as session:
        attempts = session.scalars(select(AnalysisAttempt)).all()
        assert "fixture-secret" not in json.dumps([attempt.result for attempt in attempts])
    engine.dispose()
    if failure != "timeout":
        assert report["calls"][0]["response_received"] is True
    else:
        assert report["calls"][0]["status"] == "unknown"
