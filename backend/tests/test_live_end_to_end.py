from __future__ import annotations

import json
from datetime import UTC, datetime

from bluepulse_backend import live_end_to_end
from bluepulse_backend.pipeline import Candidate, MockSourceAdapter
from bluepulse_backend.source_collection import SOURCES, collect


def test_bounded_all_source_run_and_failed_source_retry(tmp_path, monkeypatch):
    calls = []

    def fake_audit(slug, session, *, max_items):
        assert max_items == 2
        calls.append(slug)
        if slug != "europol-news" or calls.count(slug) == 1:
            return {"source": slug, "error_code": "transport_error" if slug == "europol-news" else None,
                    "candidate_count": 0, "items": []}
        spec = SOURCES[slug]
        candidate = Candidate(url=f"https://{spec.host}/test-item", title="Official test item",
                              body="Original text " * 40, published_at=datetime.now(UTC))
        collect(session, spec, MockSourceAdapter([candidate]))
        return {"source": slug, "error_code": None, "candidate_count": 1, "items": []}

    monkeypatch.setattr(live_end_to_end, "audit_source", fake_audit)
    output = tmp_path / "live"
    report = live_end_to_end.run(output, max_items=2, max_model_calls=0)
    assert report["counts"] == {"sources": 15, "materials": 0, "unique_url_mirrors": 0,
                                "analysis_attempts": 0, "public": 0}
    assert calls == list(SOURCES)
    result = live_end_to_end.retry_source(output, "europol-news")
    assert result["error_code"] is None and result["candidate_count"] == 1
    assert result["counts"]["materials"] == 1 and result["counts"]["public"] == 0
    saved = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert len(saved["source_retries"]) == 1
    assert saved["source_retries"][0]["error_code"] is None
