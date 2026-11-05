from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bluepulse_backend.live_model import LiveAnalyzer, ProviderRejected, load_local_credentials, model_listed
from bluepulse_backend.live_sources import (BoundedHTTP, GovUkAdapter, NistRssAdapter,
                                            SourceFetchError, csv_table_text, plain_text)
from bluepulse_backend.models import Material, Source


def test_govuk_adapter_uses_content_api_and_marks_attachment_intro_as_abstract():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/search.json":
            return httpx.Response(200, json={"results": [
                {"link": "/government/news/technology-story"},
                {"link": "/government/publications/attachment-only"},
                {"link": "//outside.example/unsafe"},
            ]})
        if request.url.path.endswith("technology-story"):
            return httpx.Response(200, json={"title": "Technology story", "description": "Official description",
                "first_published_at": "2026-10-20T12:00:00Z", "details": {"body": "<p>Police technology was tested.</p>"}})
        return httpx.Response(200, json={"title": "Attachment landing", "description": "See attached report",
            "first_published_at": "2026-10-19T12:00:00Z", "details": {"body": "<p>Download attached PDF.</p>", "attachments": [{}]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0), max_items=2)
        candidates = adapter.candidates()
    assert len(candidates) == 2
    assert candidates[0].body == "Police technology was tested."
    assert candidates[1].body is None and candidates[1].summary == "See attached report"
    assert len(paths) == 3
    assert adapter.diagnostics == {"search_results": 3, "detail_attempts": 2,
                                   "detail_parsed": 2, "detail_failed": 0,
                                   "attachment_attempts": 0, "attachment_parsed": 0,
                                   "attachment_failed": 0, "csv_attempts": 0,
                                   "csv_parsed": 0, "csv_failed": 0,
                                   "csv_matched_html": 0, "csv_mismatched_html": 0}
    assert adapter.item_diagnostics[1]["attachment_count"] == 1


def test_govuk_english_html_attachment_becomes_body_with_exact_provenance():
    paths = []
    attachment_path = "/government/publications/records/results-accessible"
    body = "<h2>Deployment result</h2><p>One deployment was recorded on 1 November.</p>"

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/search.json":
            return httpx.Response(200, json={"results": [{"link": "/government/publications/records"}]})
        if request.url.path.endswith(attachment_path):
            return httpx.Response(200, json={"details": {"body": body}})
        return httpx.Response(200, json={"title": "Deployment records", "description": "Landing introduction",
            "details": {"body": "<p>See the documents.</p>", "attachments": [
                {"attachment_type": "html", "title": "Results (Welsh accessible)",
                 "url": "/government/publications/records/results-welsh-accessible"},
                {"attachment_type": "html", "title": "Results (accessible)", "url": attachment_path},
                {"attachment_type": "file", "content_type": "text/csv",
                 "url": "https://assets.publishing.service.gov.uk/media/abc/results.csv"},
            ]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0),
                              max_items=1,
                              csv_fetcher=lambda url, agent: (b"Deployment,Date\nHolyhead,27/11/25\n", 404))
        candidate, = adapter.candidates()
    assert candidate.body == "Deployment result\nOne deployment was recorded on 1 November."
    assert candidate.body_source_url == "https://www.gov.uk" + attachment_path
    assert candidate.summary == "Landing introduction"
    assert paths == ["/api/search.json", "/api/content/government/publications/records",
                     "/api/content" + attachment_path]
    assert adapter.diagnostics["attachment_attempts"] == 1
    assert adapter.diagnostics["attachment_parsed"] == 1
    assert adapter.item_diagnostics[0]["attachment_body_chars"] == len(candidate.body)
    assert adapter.item_diagnostics[0]["other_text_attachment_count"] == 1
    assert adapter.item_diagnostics[0]["csv_rows"] == 1
    assert adapter.item_diagnostics[0]["csv_matches_html"] is False
    assert adapter.diagnostics["csv_mismatched_html"] == 1


def test_govuk_csv_two_level_headers_and_rows_match_html():
    payload = ("Deployment,Date,Positive,,Incorrect,\n"
               ",,Alerts,Interventions,Alerts,Interventions\n"
               "Holyhead,27/11/25,1,1,0,0\n").encode()
    csv_body, rows = csv_table_text(payload)
    assert csv_body == ("Deployment | Date | Positive Alerts | Positive Interventions | "
                        "Incorrect Alerts | Incorrect Interventions\n"
                        "Holyhead | 27/11/25 | 1 | 1 | 0 | 0")
    assert rows == [["Holyhead", "27/11/25", "1", "1", "0", "0"]]
    assert GovUkAdapter._csv_attachment_url({"attachment_type": "file", "content_type": "text/csv",
        "title": "Results", "url": "https://assets.publishing.service.gov.uk/media/abc/results.csv"})
    assert GovUkAdapter._csv_attachment_url({"attachment_type": "file", "content_type": "text/csv",
        "title": "Results (Welsh)",
        "url": "https://assets.publishing.service.gov.uk/media/abc/results-welsh.csv"}) is None


def test_govuk_csv_fills_abstract_when_html_unavailable():
    csv_url = "https://assets.publishing.service.gov.uk/media/abc/results.csv"
    csv_payload = b"Deployment,Date\nHolyhead,27/11/25\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search.json":
            return httpx.Response(200, json={"results": [{"link": "/government/publications/records"}]})
        return httpx.Response(200, json={"title": "Records", "description": "Short introduction",
            "details": {"body": "<p>Read the file.</p>", "attachments": [
                {"attachment_type": "file", "content_type": "text/csv", "title": "Results",
                 "url": csv_url}]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0),
                              max_items=1, csv_fetcher=lambda url, agent: (csv_payload, 404))
        candidate, = adapter.candidates()
    assert candidate.body == "Deployment | Date\nHolyhead | 27/11/25"
    assert candidate.body_source_url == csv_url
    assert adapter.item_diagnostics[0]["csv_rows"] == 1


def test_govuk_csv_robots_disallow_blocks_asset(monkeypatch):
    from bluepulse_backend import live_sources
    seen = []

    def fake_get(url, *, user_agent, accept, max_bytes):
        seen.append(url)
        return b"User-agent: *\nDisallow: /media/\n"

    monkeypatch.setattr(live_sources, "_asset_get", fake_get)
    with pytest.raises(SourceFetchError, match="robots_disallowed_or_delayed"):
        live_sources.fetch_govuk_csv(
            "https://assets.publishing.service.gov.uk/media/abc/results.csv", "BluePulseResearch/0.1")
    assert seen == ["https://assets.publishing.service.gov.uk/robots.txt"]


def test_govuk_csv_retries_one_transient_transport_error_after_robots_check(monkeypatch):
    from bluepulse_backend import live_sources
    seen = []

    def fake_get(url, *, user_agent, accept, max_bytes):
        seen.append(url)
        if len(seen) == 1:
            raise SourceFetchError("transport_error")
        if url.endswith("robots.txt"):
            raise SourceFetchError("http_404")
        return b"Deployment,Date\nHolyhead,27/11/25\n"

    monkeypatch.setattr(live_sources, "_asset_get", fake_get)
    monkeypatch.setattr(live_sources.time, "sleep", lambda _: None)
    data, status = live_sources.fetch_govuk_csv(
        "https://assets.publishing.service.gov.uk/media/abc/results.csv", "BluePulseResearch/0.1")
    assert status == 404 and data.startswith(b"Deployment")
    assert [url.rsplit("/", 1)[-1] for url in seen] == ["robots.txt", "robots.txt", "results.csv"]


def test_govuk_attachment_table_keeps_row_and_column_boundaries():
    html = ("<table>\n  <thead><tr>\n    <th>Deployment</th>\n    <th>Date</th>"
            "<th>Total alerts</th>\n  </tr></thead>\n"
            "<tbody><tr><td><p>Holyhead</p></td><td>10/11/25</td><td>0</td></tr>"
            "<tr><td>Holyhead</td><td>27/11/25</td><td>1</td></tr></tbody></table>")
    assert plain_text(html) == ("Deployment | Date | Total alerts\n"
                                "Holyhead | 10/11/25 | 0\nHolyhead | 27/11/25 | 1")


def test_govuk_rejects_encoded_traversal_in_attachment_path():
    assert GovUkAdapter._html_attachment_path({
        "attachment_type": "html", "url": "/government/publications/records/%2e%2e/other",
    }) is None


def test_govuk_attachment_failure_keeps_abstract_and_records_error():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/search.json":
            return httpx.Response(200, json={"results": [{"link": "/government/publications/records"}]})
        if request.url.path == "/api/content/government/publications/records":
            return httpx.Response(200, json={"title": "Records", "description": "Short description",
                "details": {"body": "<p>See the report.</p>", "attachments": [
                    {"attachment_type": "html", "title": "External",
                     "url": "//outside.example/records"},
                    {"attachment_type": "html", "title": "Missing HTML",
                     "url": "/government/publications/records/missing"},
                ]}})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0), max_items=1)
        candidate, = adapter.candidates()
    assert candidate.body is None and candidate.body_source_url is None
    assert candidate.summary == "Short description"
    assert paths[-1] == "/api/content/government/publications/records/missing"
    assert adapter.diagnostics["attachment_failed"] == 1
    assert adapter.item_diagnostics[0]["attachment_error"] == "http_404"


def test_govuk_pdf_landing_intro_is_not_treated_as_full_document():
    intro = "This page introduces the assessment but its detailed evidence is in the PDF. " * 8

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search.json":
            return httpx.Response(200, json={"results": [{"link": "/government/publications/assessment"}]})
        return httpx.Response(200, json={"title": "Assessment", "description": "Short description",
            "details": {"body": f"<p>{intro}</p>",
                        "attachments": [{"attachment_type": "file", "content_type": "application/pdf"}]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0), max_items=1)
        rows = adapter.candidates()
    assert rows[0].body is None
    assert "detailed evidence" in rows[0].summary
    assert adapter.item_diagnostics[0]["page_body_chars"] > 400


def test_nist_rss_rejects_off_host_item_and_keeps_future_date():
    future = (datetime.now(UTC) + timedelta(days=10)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    feed = f"""<rss><channel>
      <item><title>Unsafe</title><link>https://example.org/other</link></item>
      <item><title>Future event</title><link>https://www.nist.gov/news-events/events/2027/01/future-event</link></item>
      <item><title>Public safety technology</title><link>https://www.nist.gov/story</link>
      <description>&lt;p&gt;Communications study&lt;/p&gt;</description><pubDate>{future}</pubDate></item>
    </channel></rss>"""
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=feed))) as client:
        adapter = NistRssAdapter(BoundedHTTP(client, allowed_hosts={"www.nist.gov"}, delay_seconds=0), max_items=2, fetch_details=False)
        candidates = adapter.candidates()
    assert len(candidates) == 1
    assert candidates[0].summary == "Communications study"
    assert candidates[0].published_at > datetime.now(UTC)
    assert adapter.diagnostics["feed_items"] == 3 and adapter.diagnostics["feed_skipped"] == 2


def test_nist_detail_extracts_only_article_body():
    feed = """<rss><channel><item><title>Study</title><link>https://www.nist.gov/study</link>
      <description>Short summary</description></item></channel></rss>"""
    html = """<html><div>Site navigation</div><div class="text-with-summary">
      <figure><figcaption>Picture caption</figcaption></figure>
      <p>A mass spectrometry method detects substances.</p><div><p>Police may use the evidence.</p></div>
      </div><div>Related links</div></html>"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=feed if request.url.path.endswith("rss.xml") else html)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        candidates = NistRssAdapter(BoundedHTTP(client, allowed_hosts={"www.nist.gov"}, delay_seconds=0), max_items=1).candidates()
    assert candidates[0].body == "A mass spectrometry method detects substances.\nPolice may use the evidence."


def test_live_model_contract_and_bounded_input():
    requests = []
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "req-1", "model": "fixture-model",
            "usage": {"prompt_tokens": 90, "completion_tokens": 40},
            "choices": [{"message": {"content": json.dumps({
                "relevant": True, "title_zh": "警务通信技术", "summary_zh": "原文描述通信试验。",
                "topics": ["practice"], "importance_score": 61,
                "featured_candidate": False,
            }, ensure_ascii=False)}}]})

    source = Source(id="source-id", slug="nist", name="NIST", region="foreign", country_code="US",
                    language="en", source_type="official", allowed_hosts=["www.nist.gov"], topics=[])
    material = Material(id="material-id", source=source, source_id=source.id,
                        canonical_url="https://www.nist.gov/story", source_url="https://www.nist.gov/story",
                        source_title="Public safety communication", source_body="a" * 10000,
                        body_status="full_text", language="en", content_hash="x" * 64)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        analyzer = LiveAnalyzer(client, "https://model.example/v1", "fixture-key", "fixture-model")
        result = analyzer.analyze(material)
        assert analyzer.input_version != LiveAnalyzer(client, "https://model.example/v1", "fixture-key", "different-model").input_version
    assert result.relevant and result.topics == ("practice",)
    assert result.provider_meta["prompt_tokens"] == 90
    sent = json.loads(requests[0].content)
    assert len(json.loads(sent["messages"][1]["content"])["text"]) == 4200
    assert "published_date" in json.loads(sent["messages"][1]["content"])
    assert sent["max_tokens"] == 450


def test_live_model_auth_failure_stops_batch_and_credentials_not_required_in_repo(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401))) as client:
        source = Source(id="s", slug="test", name="test", region="foreign", country_code="GB",
                        language="en", source_type="official", allowed_hosts=["example.test"], topics=[])
        material = Material(id="m", source=source, source_id="s", canonical_url="https://example.test/x",
                            source_url="https://example.test/x", source_title="x", source_summary="abstract",
                            body_status="abstract_only", language="en", content_hash="x" * 64)
        with pytest.raises(ProviderRejected) as error:
            LiveAnalyzer(client, "https://model.example/v1", "fixture-key", "fixture-model").analyze(material)
        assert error.value.code == "provider_http_401" and error.value.stop_batch
    env = tmp_path / ".env"
    env.write_text('base_url=https://model.example/v1\nkey=secret\nllm_id=fixture-model\n', encoding="utf-8")
    assert load_local_credentials(env) == ("https://model.example/v1", "secret", "fixture-model")


def test_model_preflight_blocks_unlisted_id():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "data": [{"id": "TierSense", "supported_endpoint_types": ["openai"]}]
    }))) as client:
        assert model_listed(client, "https://model.example/v1", "fixture-key", "TierSense")
        assert not model_listed(client, "https://model.example/v1", "fixture-key", "missing-model")


def test_deepseek_request_disables_thinking_and_asks_for_json():
    sent = []
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '{"relevant":false,"title_zh":null,"summary_zh":null,"topics":[],"importance_score":0,"featured_candidate":false}'
        }}]})
    source = Source(id="s", slug="test", name="test", region="foreign", country_code="GB",
                    language="en", source_type="official", allowed_hosts=["example.test"], topics=[])
    material = Material(id="m", source=source, source_id="s", canonical_url="https://example.test/x",
                        source_url="https://example.test/x", source_title="x", source_summary="abstract",
                        body_status="abstract_only", language="en", content_hash="x" * 64)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        LiveAnalyzer(client, "https://api.deepseek.com", "fixture-key", "deepseek-flash").analyze(material)
    assert sent[0]["thinking"] == {"type": "disabled"}
    assert sent[0]["response_format"] == {"type": "json_object"}
