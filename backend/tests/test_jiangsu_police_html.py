from __future__ import annotations

import unittest

import httpx

from bluepulse_backend.ingestion.jiangsu_police_html import (
    _article, _listing_urls, fetch_jiangsu_police_html,
)
from bluepulse_backend.models import Source

BASE = "https://gat.jiangsu.gov.cn/col/col6372/index.html"
GOOD = "https://gat.jiangsu.gov.cn/art/2026/9/24/art_6372_11834669.html"
OTHER = "https://gat.jiangsu.gov.cn/art/2026/9/24/art_6372_11834666.html"
LISTING = b'''<html><record><![CDATA[<li><a href="/art/2026/9/24/art_6372_11834666.html">Routine police news</a></li>]]></record>
<record><![CDATA[<li><a href="/art/2026/9/24/art_6372_11834669.html">Police AI technology</a></li>]]></record>
<record><![CDATA[<li><a href="https://example.org/art/2026/9/24/art_6372_1.html">External</a></li>]]></record></html>'''
DETAIL = '''<html><head><meta name="PubDate" content="2026-09-24 10:50"></head>
<div class="wzzw-title">Police AI technology</div><div class="wzzw-article"><p>''' + "police AI application " * 10 + '''</p></div></html>'''


class JiangsuPoliceHtmlTests(unittest.TestCase):
    def test_bad_detail_does_not_discard_good_article(self) -> None:
        listing = (f'<record><![CDATA[<a href="{OTHER}">Police AI</a>]]></record>'
                   f'<record><![CDATA[<a href="{GOOD}">Police AI application</a>]]></record>').encode()

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/col/col6372/index.html":
                return httpx.Response(200, content=listing)
            if str(request.url) == OTHER:
                return httpx.Response(200, text="<html><div class='wzzw-title'>Bad</div></html>")
            return httpx.Response(200, text=DETAIL)

        stats: dict[str, int] = {}
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            articles = fetch_jiangsu_police_html(self.source(), client=client,
                                                  sleeper=lambda _: None, diagnostics=stats)
        self.assertEqual([article.url for article in articles], [GOOD])
        self.assertEqual(stats["detail_parse_failed"], 1)

    def source(self) -> Source:
        return Source(slug="jiangsu-police-news", name="Jiangsu", base_url=BASE,
                      adapter="jiangsu_police_html", config={"allowed_hosts": ["gat.jiangsu.gov.cn"],
                      "max_articles": 2, "request_delay_seconds": 1})

    def test_listing_filters_other_hosts_and_prioritizes_tech(self) -> None:
        self.assertEqual(_listing_urls(LISTING, BASE), [(OTHER, "Routine police news"),
                                                        (GOOD, "Police AI technology")])
        self.assertEqual(_article(DETAIL.encode(), GOOD).published_at.isoformat(),
                         "2026-09-24T02:50:00+00:00")

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/col/col6372/index.html":
                return httpx.Response(200, content=LISTING)
            return httpx.Response(200, text=DETAIL)

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            stats = {}
            items = fetch_jiangsu_police_html(self.source(), client=client, sleeper=lambda _: None,
                                              diagnostics=stats)
        self.assertEqual([item.url for item in items], [GOOD, OTHER])
        self.assertEqual(stats["detail_pages"], 2)

    def test_known_url_skips_detail_and_robots_disallow_stops(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(request.url.path)
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/col/col6372/index.html":
                return httpx.Response(200, content=LISTING)
            return httpx.Response(200, text=DETAIL)

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            items = fetch_jiangsu_police_html(self.source(), known_urls={GOOD}, client=client,
                                              sleeper=lambda _: None)
        self.assertEqual([item.url for item in items], [OTHER])
        self.assertNotIn(GOOD.replace("https://gat.jiangsu.gov.cn", ""), requested)

        with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        )) as client:
            with self.assertRaisesRegex(RuntimeError, "robots.txt"):
                fetch_jiangsu_police_html(self.source(), client=client, sleeper=lambda _: None)


if __name__ == "__main__":
    unittest.main()
