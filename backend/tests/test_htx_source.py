from __future__ import annotations

from datetime import date

import httpx
import pytest

from bluepulse_backend.htx_source import HOST, HtxNewsAdapter
from bluepulse_backend.live_sources import BoundedHTTP, SourceFetchError


DETAIL = "https://www.htx.gov.sg/whats-happening/all-news---events/all-news/2026/ai-pilot"


def test_htx_public_listing_to_limited_article_body_and_date():
    requests = []
    listing = {"totalItems": 2, "data": [
        {"articleType": "News", "url": "/whats-happening/all-news---events/all-news/2026/ai-pilot",
         "title": "AI pilot", "date": "29 October 2026"},
        {"articleType": "News", "url": "https://outside.example/unsafe", "title": "Outside"},
    ]}
    html = """<div class='article-detail-banner'><h1>AI pilot</h1></div>
      <meta property='og:description' content='Pilot description'>
      <div class='detail__content'><span class='date-author'><span class='date'>Published on 29 October 2026</span></span>
      <div class='rte'><p>Police officers tested the AI pilot in a documented setting with safeguards.</p></div>
      <div class='rte'><p>Outcomes were measured against a manual baseline and reviewed by staff.</p></div>
      <div class='rte'><p><strong>Photo Gallery</strong></p></div></div>
      <footer><p>Unrelated site navigation</p></footer>"""

    def handler(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /Sitefinity/\n")
        if request.url.path.endswith("GetNewsAndEventsListing"):
            assert request.url.params["type"] == "News" and request.url.params["topic"] == "all"
            return httpx.Response(200, json=listing)
        return httpx.Response(200, text=html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = HtxNewsAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                 max_items=2, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert len(rows) == 1 and rows[0].url == DETAIL
    assert rows[0].published_date == date(2026, 10, 29)
    assert rows[0].published_at is None
    assert len(rows[0].body) >= 120 and "Unrelated" not in rows[0].body
    assert "Photo Gallery" not in rows[0].body
    assert len(requests) == 3
    assert adapter.diagnostics == {"listing_items": 2, "detail_attempts": 1,
                                   "detail_full_text": 1, "detail_failed": 0}


def test_htx_robots_disallow_stops_before_listing():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /HTXInterface/\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = HtxNewsAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                 sleeper=lambda _: None)
        with pytest.raises(SourceFetchError, match="robots_disallowed_or_delayed"):
            adapter.candidates()
    assert requests == ["https://www.htx.gov.sg/robots.txt"]
