from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

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


def classification_step(category, *, label="PASS"):
    def step(kind, purpose, prompt, inputs, tokens):
        if kind == "prefilter":
            return {"label": label}, {}
        if kind == "structure":
            return {"scope": "unknown", "category": category, "tags": []}, {}
        if kind == "score":
            return {"content_type": "industry_event", "sig": 8, "nov": 8, "cred": 8,
                    "reson": 8, "act": 8}, {"request_id": purpose}
        return {"titleZh": "警务科技线索", "summaryZh": "报道提供了具体的技术应用线索。"}, {}
    return step


@pytest.mark.parametrize("category", ["product", "practice", "paper", "law", "embodied",
                                     "public-opinion", "low-altitude", "other"])
def test_related_news_keeps_its_explicit_main_category(category):
    from bluepulse_backend.editorial import analyze

    row = Material(source_title="Technology clues", source_body="Police technology evidence. " * 20,
                   body_status="full_text", source=Source(selection_threshold=60))
    result = analyze(row, classification_step(category))
    assert result.topics == (category,)
    assert result.candidate and result.score == 80


@pytest.mark.parametrize("category", [None, "", "unsupported", [], {}])
def test_incomplete_or_invalid_classification_is_an_error_not_irrelevance(category):
    from bluepulse_backend.editorial import analyze

    row = Material(source_title="Technology clues", source_body="Police technology evidence. " * 20,
                   body_status="full_text", source=Source(selection_threshold=60))
    with pytest.raises(ValueError, match="invalid_structure_category"):
        analyze(row, classification_step(category))


def test_irrelevant_news_stops_before_other_classification():
    from bluepulse_backend.editorial import analyze

    row = Material(source_title="Ordinary community visit", source_body="Police visited residents.",
                   body_status="full_text", source=Source(selection_threshold=60))

    def step(kind, *args):
        assert kind == "prefilter"
        return {"label": "BLOCK"}, {}

    result = analyze(row, step)
    assert result.label == "BLOCK" and result.topics == () and not result.candidate
