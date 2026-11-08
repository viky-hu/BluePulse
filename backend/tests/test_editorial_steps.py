from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from bluepulse_backend.models import Material, Source


def test_two_scores_and_structure_feed_grounded_writing():
    from bluepulse_backend.editorial import analyze

    row = Material(source_title="Police dispatch trial",
                   source_body="The city police started a dispatch trial.",
                   body_status="full_text", source=Source(selection_threshold=60))
    barrier = Barrier(2, timeout=3)
    calls = []

    def step(kind, purpose, prompt, inputs, tokens):
        calls.append(purpose)
        if purpose in {"structure", "score:1"}:
            barrier.wait()
        if kind == "prefilter":
            return {"label": "PASS"}, {}
        if kind == "score":
            return {"content_type": "industry_event", "sig": 7, "nov": 7, "cred": 7,
                    "reson": 7, "act": 7}, {"request_id": purpose}
        if kind == "structure":
            return {"scope": "single", "category": "practice", "tags": [],
                    "fact": {"title": "试点", "evidence": "started a dispatch trial",
                             "conditions": [{"quote": "no proof of an outcome"}]}}, {}
        assert purpose == "understand"
        return {"titleZh": "警务调度试点", "summaryZh": "城市警察启动调度试点。"}, {}

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(analyze, row, step).result()
    assert result.candidate and result.score == 70
    assert result.fact["conditions"] == []
    assert sorted(calls) == ["prefilter", "score:1", "score:2", "structure", "understand"]


def test_translation_rejects_repeated_shielded_links():
    from bluepulse_backend.editorial import translate

    def step(*args):
        return {"blocks": ["参见 ⟦0⟧ ⟦0⟧"]}, {}

    import pytest
    with pytest.raises(ValueError, match="translation_tokens"):
        translate("See https://example.test/docs", step)
