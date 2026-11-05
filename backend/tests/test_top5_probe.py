from __future__ import annotations

import httpx

from bluepulse_backend.top5_probe import HtmlEvidenceProbe, probe
from bluepulse_backend.live_sources import BoundedHTTP


def test_npcc_probe_discovers_detail_body_and_date():
    url = "https://news.npcc.police.uk/releases/police-technology-update"
    body = "A police technology programme tested a new digital evidence workflow. " * 4

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.path == "/releases":
            return httpx.Response(200, text=f"<a class='card__link' href='{url}'>Technology update</a>")
        return httpx.Response(200, text=(f"<h1 class='content-title'>Technology update</h1>"
                                         f"<p class='date'>29 Oct 2026</p>"
                                         f"<div class='content-body'><p>{body}</p></div>"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = HtmlEvidenceProbe(BoundedHTTP(client, allowed_hosts={"news.npcc.police.uk"}, delay_seconds=0),
                                    kind="npcc", max_items=1, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert len(rows) == 1 and body.strip() in rows[0].body
    assert rows[0].published_date.isoformat() == "2026-10-29"
    assert rows[0].published_at is None
    assert adapter.diagnostics["detail_body"] == 1


def test_jiangsu_probe_parses_record_and_meta_date():
    url = "https://gat.jiangsu.gov.cn/art/2026/10/29/art_6372_123.html"
    body = "江苏公安机关开展人工智能技术在公共安全领域的应用试点，介绍系统建设、工作流程和数据治理边界。" * 3

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/col/col6372/index.html":
            return httpx.Response(200, text=f"<record><![CDATA[<a href='{url}'>人工智能警务试点</a>]]></record>")
        return httpx.Response(200, text=("<meta name='PubDate' content='2026-10-29 14:20'>"
                                         "<meta name='ContentSource' content='人民公安报'>"
                                         "<h1 class='wzzw-title'>人工智能警务试点</h1>"
                                         f"<div class='wzzw-article'><p>{body}</p></div>"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = HtmlEvidenceProbe(BoundedHTTP(client, allowed_hosts={"gat.jiangsu.gov.cn"}, delay_seconds=0),
                                    kind="jiangsu", max_items=1, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert len(rows) == 1 and rows[0].url == url
    assert rows[0].published_at.isoformat() == "2026-10-29T06:20:00+00:00"
    assert adapter.diagnostics["robots_unavailable"] == 1
    assert adapter.item_diagnostics[0]["content_source"] == "人民公安报"


def test_probe_reports_robots_rejection_without_requesting_listing():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /releases\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe("npcc", client, max_items=1)
    assert result["status"] == "failed" and result["error_code"] == "robots_disallowed"
    assert requests == ["/robots.txt"]


def test_govuk_probe_finds_text_in_html_attachment_without_calling_file_asset():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/api/search.json":
            return httpx.Response(200, json={"results": [{"link": "/government/publications/example"}]})
        if request.url.path == "/api/content/government/publications/example":
            return httpx.Response(200, json={
                "title": "Example", "description": "Short introduction",
                "details": {"body": "<p>See the documents.</p>", "attachments": [
                    {"attachment_type": "html", "url": "/government/publications/example/full-text"},
                    {"attachment_type": "file", "content_type": "application/pdf", "url": "https://assets.publishing.service.gov.uk/example.pdf"},
                ]},
            })
        if request.url.path == "/api/content/government/publications/example/full-text":
            return httpx.Response(200, json={"details": {"body": "<p>Full text evidence for classification.</p>"}})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = probe("govuk", client, max_items=1)
    item = result["items"][0]
    assert item["evidence"] == "full_text"
    assert item["html_attachment_count"] == 1
    assert item["html_attachment_body_chars"] == len("Full text evidence for classification.")
    assert paths == ["/api/search.json", "/api/content/government/publications/example",
                     "/api/content/government/publications/example/full-text"]
