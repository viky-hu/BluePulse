from __future__ import annotations

from datetime import UTC, datetime

import httpx

from bluepulse_backend.live_sources import BoundedHTTP
from bluepulse_backend.statescoop_source import FEED, HOST, StateScoopAdapter


ARTICLE = "https://statescoop.com/police-ai-evidence-review/"


def test_tag_feed_extracts_full_body_without_ads_or_page_chrome():
    feed = f"""<rss><channel><item><title>Police AI evidence review</title><link>{ARTICLE}</link>
      <pubDate>Thu, 29 Oct 2026 19:33:12 +0000</pubDate>
      <description>How police review AI evidence.</description></item></channel></rss>"""
    sentence = "Police teams reviewed the model output against source evidence. " * 4
    html = ("<meta property='article:published_time' content='2026-10-29T19:33:12+00:00'>"
            "<h1 class='single-article__title'>Police AI evidence review</h1>"
            "<div class='single-article__content-inner'><html><body>"
            f"<p>{sentence}</p><div class='ad'><p>Advertisement only</p></div>"
            "<p>Investigators documented limitations and human checks.</p>"
            "</body></html></div><aside>Unrelated article</aside>")
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: GPTBot\nDisallow: /\nUser-agent: *\nDisallow:\n")
        if str(request.url) == FEED:
            return httpx.Response(200, text=feed)
        if str(request.url) == ARTICLE:
            return httpx.Response(200, text=html)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = StateScoopAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                    max_items=1, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert requested == [f"https://{HOST}/robots.txt", FEED, ARTICLE]
    assert len(rows) == 1 and rows[0].title == "Police AI evidence review"
    assert sentence.strip() in rows[0].body
    assert "Advertisement" not in rows[0].body and "Unrelated" not in rows[0].body
    assert rows[0].published_at == datetime(2026, 10, 29, 19, 33, 12, tzinfo=UTC)


def test_robots_disallow_stops_before_feed_request():
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /tag/\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = StateScoopAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                    max_items=1, sleeper=lambda _: None)
        try:
            adapter.candidates()
        except Exception as exc:
            assert getattr(exc, "code", None) == "robots_disallowed_or_delayed"
        else:
            assert False, "disallow must stop collection"
    assert requested == ["/robots.txt"]
