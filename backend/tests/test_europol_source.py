from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from bluepulse_backend.europol_source import FEED, HOST, EuropolNewsAdapter
from bluepulse_backend.live_sources import BoundedHTTP
from bluepulse_backend.source_collection import SOURCES, build_adapter


DETAIL = "https://www.europol.europa.eu/media-press/newsroom/news/digital-forensics-report"


def test_official_feed_extracts_intro_body_and_original_timestamp():
    feed = f"""<rss><channel>
      <item><title>Unrelated arrests</title><link>https://www.europol.europa.eu/media-press/newsroom/news/arrests</link></item>
      <item><title>Digital forensics report</title><link>{DETAIL}</link><description>Police technology</description></item>
    </channel></rss>"""
    node = {"NodeLoader": {"node": {
        "alias": "/media-press/newsroom/news/digital-forensics-report",
        "title": "Digital forensics report", "published": 1792142216,
        "introduction": "<p>Officers need reliable digital evidence.</p>",
        "body": "<p>Investigators tested a forensic method and documented its limits.</p>" * 4,
        "summary": "A report about evidence workflows.",
    }}}
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        if str(request.url) == FEED:
            return httpx.Response(200, text=feed)
        if str(request.url) == DETAIL:
            return httpx.Response(200, text="<script>window.SERVER_DATA=" + json.dumps(node) + ";</script>")
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = build_adapter(SOURCES["europol-news"], client, max_items=1)
        adapter.http.delay_seconds = 0
        adapter.sleeper = lambda _: None
        rows = adapter.candidates()
    assert requested == [f"https://{HOST}/robots.txt", FEED, DETAIL]
    assert adapter.diagnostics["feed_items"] == 2 and adapter.diagnostics["topic_matches"] == 1
    assert len(rows) == 1 and rows[0].title == "Digital forensics report"
    assert rows[0].body.startswith("Officers need reliable digital evidence.")
    assert "documented its limits" in rows[0].body
    assert rows[0].published_at == datetime.fromtimestamp(1792142216, tz=UTC)


def test_detail_alias_mismatch_fails_closed():
    feed = f"<rss><channel><item><title>Digital forensics</title><link>{DETAIL}</link></item></channel></rss>"
    node = {"NodeLoader": {"node": {"alias": "/wrong-page", "title": "Wrong page",
                                      "published": 1792142216, "body": "A" * 200}}}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        if str(request.url) == FEED:
            return httpx.Response(200, text=feed)
        return httpx.Response(200, text="<script>window.SERVER_DATA=" + json.dumps(node) + ";</script>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = EuropolNewsAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                     max_items=1, sleeper=lambda _: None)
        try:
            adapter.candidates()
        except Exception as exc:
            assert getattr(exc, "code", None) == "all_details_failed"
        else:
            assert False, "mismatched detail must not enter the pipeline"
    assert adapter.diagnostics["detail_failed"] == 1
