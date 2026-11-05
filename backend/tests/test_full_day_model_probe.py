from __future__ import annotations

import json
from datetime import date

import httpx

from bluepulse_backend import full_day_model_probe
from bluepulse_backend.source_collection import SOURCES


def test_four_call_model_probe_is_capped_and_nonpublic(tmp_path, monkeypatch):
    cases = [
        ("htx-news", "positive_product", "direct", True, "product"),
        ("nist-public-safety", "positive_paper", "direct", True, "paper"),
        ("ccgp-policing-tech", "off_topic", "off", True, None),
        ("govuk", "thin_evidence", "direct", False, "practice"),
    ]
    rows = []
    sample = {"sample_day": "2026-11-01", "items": []}
    for slug, case, fit, sufficient, topic in cases:
        url = f"https://{SOURCES[slug].host}/pilot/{case}"
        sample["items"].append({"source": slug, "url": url, "case": case})
        rows.append({"source": slug, "url": url, "topic_fit": fit,
                     "evidence_sufficient": sufficient, "primary_topic": topic,
                     "item": {"url": url, "title": case, "body": "Evidence body " * 50,
                              "summary": None, "published_at": None,
                              "published_date": "2026-11-01"}})
    monkeypatch.setattr(full_day_model_probe, "_sample", lambda *_: (date(2026, 11, 1), rows))
    sample_file = tmp_path / "sample.json"
    sample_file.write_text(json.dumps(sample), encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("base_url=https://model.example/v1\nkey=fixture-secret\nllm_id=fixture-model\n",
                   encoding="utf-8")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "fixture-model"}]})
        calls.append(request)
        user = json.loads(json.loads(request.content)["messages"][1]["content"])
        case = user["url"].rsplit("/", 1)[-1]
        topic = {"positive_product": "product", "positive_paper": "paper"}.get(case)
        result = {"relevant": bool(topic), "title_zh": "测试", "summary_zh": "内部测试摘要" if topic else None,
                  "topics": [topic] if topic else [], "importance_score": 20,
                  "featured_candidate": False}
        return httpx.Response(200, json={"id": case, "model": "fixture-model",
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                         "choices": [{"message": {"content": json.dumps(result)}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = full_day_model_probe.run(tmp_path, tmp_path / "unused.json", sample_file,
                                          tmp_path / "out", env, max_model_calls=4, client=client)
    assert report["calls_started"] == 4 and len(calls) == 4
    assert report["public"] == 0
    assert all(item["relevance_match"] is True for item in report["items"])
    assert all(item["primary_topic_in_model"] is True for item in report["items"][:2])
    assert "fixture-secret" not in (tmp_path / "out/result.json").read_text(encoding="utf-8")
