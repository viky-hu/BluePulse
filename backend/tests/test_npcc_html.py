from __future__ import annotations

import unittest
from datetime import UTC, datetime

import httpx

from bluepulse_backend.ingestion.npcc_html import (
    _article, _check_url, _listing_candidates, fetch_npcc_html,
)
from bluepulse_backend.models import Source

BASE = "https://news.npcc.police.uk/releases"
GOOD = f"{BASE}/police-ai-reporting-pilot"
OTHER = f"{BASE}/routine-weapons-amnesty"
BAD = f"{BASE}/police-drone-update"
LISTING = f'''<main>
<div class="card__body"><time class="card__date">25 Sep 2026</time><h3>
<a class="card__link" href="/releases/police-ai-reporting-pilot">Police AI reporting pilot</a></h3>
<div class="card__summary">Online crime reporting trial</div></div>
<div class="card__body"><time class="card__date">24 Sep 2026</time><h3>
<a class="card__link" href="/releases/routine-weapons-amnesty">Weapons amnesty</a></h3></div>
<div class="card__body"><time class="card__date">23 Sep 2026</time><h3>
<a class="card__link" href="/releases/police-drone-update">Police drone update</a></h3></div>
<div class="card__body"><a class="card__link" href="https://example.org/releases/police-ai">
Police AI external</a></div></main>'''
DETAIL = '''<main><p class="date">25 Sep 2026</p><h1 class="content-title">Police AI reporting pilot</h1>
<div class="content-body"><p>''' + "Police AI helps officers receive online reports. " * 8 + '''</p></div>
<div class="contact-info">Do not include contact info</div></main>'''


class NpccHtmlTests(unittest.TestCase):
    def source(self) -> Source:
        return Source(slug="npcc-policing-tech", name="NPCC", adapter="npcc_html",
                      base_url=BASE, config={"allowed_hosts": ["news.npcc.police.uk"],
                                             "max_articles": 2, "max_age_days": 90})

    def test_listing_restricts_host_and_filters_non_technology_news(self) -> None:
        candidates = _listing_candidates(LISTING.encode(), BASE)
        self.assertEqual([row[0] for row in candidates], [GOOD, BAD])
        self.assertEqual(_article(DETAIL.encode(), GOOD, None).published_at,
                         datetime(2026, 9, 25, tzinfo=UTC))
        self.assertNotIn("contact info", _article(DETAIL.encode(), GOOD, None).body)
        with self.assertRaises(ValueError):
            _check_url("https://example.org/releases/police-ai", listing=False)

    def test_known_and_bad_detail_are_isolated(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/releases":
                return httpx.Response(200, text=LISTING)
            if str(request.url) == BAD:
                return httpx.Response(200, text="<main><h1>No body</h1></main>")
            return httpx.Response(200, text=DETAIL)

        stats: dict[str, int] = {}
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            articles = fetch_npcc_html(self.source(), client=client, sleeper=lambda _: None,
                                       diagnostics=stats, now=datetime(2026, 10, 6, tzinfo=UTC))
        self.assertEqual([item.url for item in articles], [GOOD])
        self.assertEqual(stats["detail_parse_failed"], 1)
        self.assertNotIn(OTHER, requested)

        requested.clear()
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            articles = fetch_npcc_html(self.source(), known_urls={GOOD, BAD}, client=client,
                                       sleeper=lambda _: None, now=datetime(2026, 10, 6, tzinfo=UTC))
        self.assertEqual(articles, [])
        self.assertNotIn(GOOD, requested)
        self.assertNotIn(BAD, requested)

    def test_robots_disallow_stops_before_listing(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(RuntimeError, "robots.txt"):
                fetch_npcc_html(self.source(), client=client, sleeper=lambda _: None)
        self.assertEqual(requested, ["https://news.npcc.police.uk/robots.txt"])

    def test_changed_listing_is_reported_as_failure_not_empty_news(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(200, text="<html><h1>Verify your access</h1></html>")

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(RuntimeError, "no release links"):
                fetch_npcc_html(self.source(), client=client, sleeper=lambda _: None)


if __name__ == "__main__":
    unittest.main()
