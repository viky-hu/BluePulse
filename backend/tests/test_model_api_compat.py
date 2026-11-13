from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.live_model import LiveAnalyzer, ProviderRejected
from bluepulse_backend.models import AnalysisAttempt, Material, Source
from bluepulse_backend.pipeline import UnknownOutcome, process_pending
from bluepulse_backend.selection_scoring import process_selection


AUTODL = "https://www.autodl.art/api/v1"
MODEL = "DeepSeek-V4.1-Flash-1017"
CLASSIFICATION = {"relevant": True, "title_zh": "无人机搜救演练计划",
                  "summary_zh": "测试材料描述计划开展的搜救演练，尚未部署。", "topics": ["practice"]}
SCORE = {"content_type": "research_paper", "sig": 5, "nov": 4,
         "cred": 3, "reson": 4, "act": 5}


def material():
    return Material(source=Source(slug="fixture", name="Fictional test fixture"),
                    source_title="Fictional drone search-and-rescue trial plan",
                    source_url="https://example.test/fixture", source_body="Planned police drone trial. " * 30,
                    body_status="full_text", language="en", content_hash="x" * 64,
                    canonical_url="https://example.test/fixture", revision=1,
                    state="analysis_pending", relevant=True, public=False)


def envelope(content, **overrides):
    return {"id": "request-fixture", "model": MODEL,
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            "choices": [{"finish_reason": "stop", "message": {"content": content}}], **overrides}


@pytest.mark.parametrize("method,answer,limit", [("analyze", CLASSIFICATION, 1024), ("score", SCORE, 512)])
def test_autodl_parameters_shared_by_classification_and_score(method, answer, limit):
    sent = []
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(json.dumps(answer)))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        analyzer = LiveAnalyzer(client, AUTODL, "fixture-secret", MODEL)
        result = getattr(analyzer, method)(material())
    assert sent[0]["thinking"] == {"type": "disabled"}
    assert sent[0]["response_format"] == {"type": "json_object"}
    assert sent[0]["stream"] is False
    assert sent[0]["max_tokens"] == limit
    assert result.provider_meta["http_status"] == 200
    assert result.provider_meta["finish_reason"] == "stop"
    assert result.provider_meta["usage"]["prompt_tokens"] == 50


@pytest.mark.parametrize("base,model", [("https://model.example/v1", MODEL),
                                        (AUTODL, "some-other-model"),
                                        ("https://www.autodl.art.evil.test/api/v1", MODEL)])
def test_autodl_options_do_not_leak_to_other_providers_or_models(base, model):
    sent = []
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=envelope(json.dumps(CLASSIFICATION)))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        LiveAnalyzer(client, base, "fixture-secret", model).analyze(material())
    assert sent[0]["max_tokens"] == 450
    assert "thinking" not in sent[0] and "response_format" not in sent[0]


@pytest.mark.parametrize("host,model,disabled", [
    ("api.scnet.cn", "DeepSeek-V4.1-Flash-1017-Event", True),
    ("api.scnet.cn", "DeepSeek-R1-Distill", False),
    ("api.scnet.cn.example.test", "DeepSeek-V4.1-Flash-1017-Event", False),
])
def test_scnet_deepseek_v4_uses_openai_thinking_switch(host, model, disabled):
    def handler(request):
        payload = json.loads(request.content)
        assert payload.get("enable_thinking") is (False if disabled else None)
        assert "thinking" not in payload
        assert payload["max_tokens"] == 400
        return httpx.Response(200, json=envelope('{"label":"PASS"}'))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        analyzer = LiveAnalyzer(client, f"https://{host}/api/llm/v1", "fixture-secret", model)
        data, _, _ = analyzer._chat("prefilter", "source", 400)
    assert data == {"label": "PASS"}


@pytest.mark.parametrize("method", ["analyze", "score"])
@pytest.mark.parametrize("response,code", [
    (envelope("", choices=[{"finish_reason": "length", "message": {
        "content": "", "reasoning_content": "not a final answer"}}],
        usage={"completion_tokens": 450, "completion_tokens_details": {"reasoning_tokens": 450}}),
     "provider_output_truncated"),
    (envelope("  "), "provider_empty_content"),
    (envelope("not JSON"), "provider_invalid_json"),
    (envelope("{}"), "provider_invalid_schema"),
])
def test_distinct_parse_errors_keep_diagnostics_without_reasoning(method, response, code):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))) as client:
        with pytest.raises(ProviderRejected) as error:
            getattr(LiveAnalyzer(client, AUTODL, "fixture-secret", MODEL), method)(material())
    assert error.value.code == code
    assert error.value.provider_meta["http_status"] == 200
    assert error.value.provider_meta["request_id"] == "request-fixture"
    assert error.value.provider_meta["duration_ms"] >= 0
    assert "not a final answer" not in json.dumps(error.value.provider_meta)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 429])
def test_http_rejections_make_one_request_without_parameter_fallback(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "fixture-secret"}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderRejected) as error:
            LiveAnalyzer(client, AUTODL, "fixture-secret", MODEL).analyze(material())
    assert len(calls) == 1 and error.value.code == f"provider_http_{status}"
    assert error.value.provider_meta["http_status"] == status
    assert "fixture-secret" not in str(error.value) + json.dumps(error.value.provider_meta)


def test_timeout_is_unknown_and_never_retried():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture-secret", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnknownOutcome):
            LiveAnalyzer(client, AUTODL, "fixture-secret", MODEL).analyze(material())
    assert len(calls) == 1


@pytest.mark.parametrize("method", ["analyze", "score"])
def test_abnormal_provider_finish_reason_is_redacted_in_failure_diagnostics(method):
    response = envelope("invalid JSON", choices=[{"finish_reason": "echo-fixture-secret",
                                                  "message": {"content": "invalid JSON"}}])
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))) as client:
        with pytest.raises(ProviderRejected) as error:
            getattr(LiveAnalyzer(client, AUTODL, "fixture-secret", MODEL), method)(material())
    assert error.value.code == "provider_invalid_json"
    assert "fixture-secret" not in json.dumps(error.value.provider_meta)


def test_autodl_identity_binds_effective_parameters_and_fits_database():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        baseline = LiveAnalyzer(client, AUTODL, "secret-one", MODEL)
        changed = LiveAnalyzer(client, AUTODL, "secret-two", MODEL, max_output_tokens=1200)
        other_host = LiveAnalyzer(client, "https://autodl.art/api/v1", "secret-one", MODEL)
        assert baseline.input_version != changed.input_version
        assert baseline.input_version != other_host.input_version
        assert baseline.input_version == LiveAnalyzer(client, AUTODL, "different-key", MODEL).input_version
        assert baseline.selection_input_version != changed.selection_input_version
        assert len(baseline.input_version) <= 50
        assert len(baseline.selection_input_version + "-r2") <= 50


@pytest.mark.parametrize("module", ["source_worker", "source_collection", "classify_sources",
    "auto_publication", "live_pilot", "live_pilot_resume", "live_end_to_end",
    "full_day_model_probe", "real_article_pilot"])
def test_all_model_cli_defaults_and_explicit_env_override(module, monkeypatch, tmp_path):
    captured = []
    class Captured(Exception):
        pass
    def capture(parser, *args, **kwargs):
        captured.append(parser.get_default("env"))
        for action in parser._actions:
            action.required = False
        override = tmp_path / "explicit.env"
        parsed = original(parser, ["--env", str(override)])
        assert parsed.env == override
        raise Captured
    original = argparse.ArgumentParser.parse_args
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", capture)
    with pytest.raises(Captured):
        importlib.import_module("bluepulse_backend." + module).main()
    assert captured == [Path(__file__).resolve().parents[1] / ".env"]


@pytest.mark.parametrize("stage", ["classification", "score"])
def test_old_inflight_attempt_blocks_paid_calls_after_configuration_change(tmp_path, stage):
    engine = make_engine(f"sqlite:///{(tmp_path / 'inflight.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        row = material()
        if stage == "score":
            row.state = "publication_hidden"
        session.add(row)
        session.commit()
        session.add(AnalysisAttempt(material_id=row.id, revision=1, attempt=1, status="started",
                                    input_version="old-config-r1" if stage == "score" else "old-config"))
        session.commit()
        with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("must not resend"))) as client:
            analyzer = LiveAnalyzer(client, AUTODL, "secret", MODEL)
            if stage == "classification":
                assert process_pending(session, analyzer)["unknown"] == 1
            else:
                assert process_selection(session, row, analyzer, max_calls=2)["status"] == "unknown"
        assert len(session.scalars(select(AnalysisAttempt)).all()) == 1
    engine.dispose()
