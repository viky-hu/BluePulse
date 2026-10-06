from __future__ import annotations

import unittest
from datetime import UTC, datetime

import httpx

from bluepulse_backend.ingestion.nij_html import fetch_nij_html
from bluepulse_backend.models import Source


def source() -> Source:
    return Source(
        slug="nij-policing-tech", name="NIJ",
        base_url="https://nij.ojp.gov/library/articles/list?subtopic=304581",
        adapter="nij_html", source_type="government",
        config={"allowed_hosts": ["nij.ojp.gov"], "max_articles": 2, "request_delay_seconds": 1},
    )


class NijHtmlTests(unittest.TestCase):
    def test_bad_detail_does_not_discard_other_articles(self) -> None:
        bad = "https://nij.ojp.gov/topics/articles/broken"
        good = "https://nij.ojp.gov/topics/articles/good"

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if request.url.path == "/library/articles/list":
                return httpx.Response(200, text=(
                    f'<main><article class="listing-item--article"><a href="{bad}">Broken</a></article>'
                    f'<article class="listing-item--article"><a href="{good}">Good</a></article></main>'
                ))
            if str(request.url) == bad:
                return httpx.Response(200, text="<main><h1>Broken</h1></main>")
            return httpx.Response(200, text=(
                "<main><h1>Good police technology</h1><div class='field--name-body'>"
                + "<p>Police technology evidence and operational evaluation.</p>" * 4
                + "</div></main>"
            ))

        stats: dict[str, int] = {}
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            articles = fetch_nij_html(source(), client=client, sleeper=lambda _: None,
                                      diagnostics=stats)
        self.assertEqual([article.url for article in articles], [good])
        self.assertEqual(stats["detail_parse_failed"], 1)

    def test_known_article_skips_detail_and_parses_new_article(self) -> None:
        old_url = "https://nij.ojp.gov/topics/articles/known-tech"
        new_url = "https://nij.ojp.gov/topics/articles/new-body-camera"
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            requested.append(url)
            if url.endswith("/robots.txt"):
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if "/library/articles/list" in url:
                return httpx.Response(200, text=(
                    '<main><article class="listing-item--article"><a href="/topics/articles/known-tech">Old</a></article>'
                    '<article class="listing-item--article"><a href="/topics/articles/new-body-camera">New</a></article>'
                    '<article class="listing-item--article"><a href="https://evil.example/articles/other">Other</a></article>'
                    '</main>'
                ))
            if url == new_url:
                return httpx.Response(200, text=(
                    '<main><h1>New body camera research</h1>'
                    '<div class="field--name-field-date-published">Date Published September 25, 2026</div>'
                    '<div class="field--name-body"><p>Police departments tested body-worn cameras '
                    'for evidence collection. The study assessed implementation and officer training. '
                    'It reports observed outcomes without claiming a procurement contract.</p></div></main>'
                ))
            raise AssertionError(f"Unexpected request: {url}")

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            stats: dict[str, int] = {}
            articles = fetch_nij_html(
                source(), known_urls={old_url}, client=client,
                sleeper=lambda _seconds: None, diagnostics=stats,
            )
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].url, new_url)
        self.assertEqual(articles[0].parse_status, "full_text")
        self.assertEqual(articles[0].published_at, datetime(2026, 9, 25, tzinfo=UTC))
        self.assertIn("evidence collection", articles[0].body)
        self.assertEqual(stats["known_skipped"], 1)
        self.assertEqual(stats["detail_pages"], 1)
        self.assertNotIn(old_url, requested)
        self.assertFalse(any("evil.example" in url for url in requested))

    def test_robots_disallow_stops_before_listing(self) -> None:
        requests: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            return httpx.Response(200, text="User-agent: *\nDisallow: /library/articles/list\n")

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(RuntimeError, "robots.txt"):
                fetch_nij_html(source(), client=client, sleeper=lambda _seconds: None)
        self.assertEqual(requests, ["https://nij.ojp.gov/robots.txt"])

    def test_non_whitelisted_listing_is_rejected(self) -> None:
        item = source()
        item.base_url = "https://nij.ojp.gov/search/?q=police"
        with self.assertRaisesRegex(ValueError, "NIJ 列表 URL"):
            fetch_nij_html(item, sleeper=lambda _seconds: None)


if __name__ == "__main__":
    unittest.main()
