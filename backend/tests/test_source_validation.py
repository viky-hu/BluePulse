from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base
from bluepulse_backend.live_sources import BoundedHTTP, SourceFetchError
from bluepulse_backend import source_validation
from bluepulse_backend.source_validation_summary import summarize


def test_bounded_response_capture_only_after_size_check():
    captured = []
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"12345"))) as client:
        http = BoundedHTTP(client, allowed_hosts={"example.test"}, max_bytes=4,
                           delay_seconds=0, on_body=lambda url, body: captured.append((url, body)))
        with pytest.raises(SourceFetchError, match="response_too_large"):
            http.get("https://example.test/article")
    assert captured == []


def test_summary_excludes_same_snapshot_repeat_from_ingest_totals(tmp_path):
    sample = {"run_at": "2026-11-01T120000+0800", "sources": [{
        "source": "sample", "robots_status": 200,
        "diagnostics": {"listing_links": 3, "detail_attempts": 2},
        "candidate_count": 2, "body_status": {"full_text": 2}, "date_covered": 2,
        "ingest_first": {"discoveries": {"new": 2}},
        "ingest_repeat_same_snapshot": {"discoveries": {"duplicate": 2}},
        "error_code": None, "duration_seconds": 4.5,
    }]}
    (tmp_path / "baseline-one.json").write_text(json.dumps(sample), encoding="utf-8")
    (tmp_path / "review-one.json").write_text(json.dumps({
        "run_at": sample["run_at"], "items": [{"source": "sample", "url": "https://example.test/a",
        "page_checked": True, "body_clean": True,
        "evidence_sufficient": True, "editorial_fit": False}]}), encoding="utf-8")
    row, = summarize(tmp_path)
    assert (row["day"], row["source"], row["discovered_max"]) == ("2026-11-01", "sample", 3)
    assert (row["new"], row["duplicate"], row["full_text"]) == (2, 0, 2)
    assert (row["reviewed_urls"], row["evidence_sufficient"], row["editorial_fit"]) == (1, 1, 0)
    assert (row["original_pages_checked"], row["clean_body_confirmed"]) == (1, 1)


def test_govuk_robots_disallow_stops_before_search(monkeypatch):
    requests = []
    real_client = httpx.Client

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /api/search.json\n")

    monkeypatch.setattr(source_validation.httpx, "Client", lambda **kwargs:
                        real_client(transport=httpx.MockTransport(handler), **kwargs))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = source_validation.audit_source("govuk", session, max_items=1)
    assert result["error_code"] == "robots_disallowed_or_delayed"
    assert requests == ["/robots.txt"]
    assert result["candidate_count"] == 0


def test_govuk_robots_disallow_attachment_keeps_landing_as_abstract(monkeypatch):
    paths = []
    real_client = httpx.Client

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=(
                "User-agent: *\n"
                "Disallow: /api/content/government/publications/records/full-text\n"))
        if request.url.path == "/api/search.json":
            return httpx.Response(200, json={"results": [{"link": "/government/publications/records"}]})
        if request.url.path == "/api/content/government/publications/records":
            return httpx.Response(200, json={"title": "Records", "description": "Short introduction",
                "details": {"body": "<p>See attached document.</p>", "attachments": [
                    {"attachment_type": "html", "url": "/government/publications/records/full-text"}]}})
        raise AssertionError("disallowed attachment was requested")

    monkeypatch.setattr(source_validation.httpx, "Client", lambda **kwargs:
                        real_client(transport=httpx.MockTransport(handler), **kwargs))
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = source_validation.audit_source("govuk", session, max_items=1)
    assert result["error_code"] is None and result["body_status"] == {"abstract_only": 1}
    assert result["item_diagnostics"][0]["attachment_error"] == "robots_disallowed"
    assert paths == ["/robots.txt", "/api/search.json",
                     "/api/content/government/publications/records"]
