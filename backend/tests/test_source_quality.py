from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from bluepulse_backend.editorial import public_article_conditions
from bluepulse_backend.ingestion.adapters import (
    SourceAccessChallenge, _abstract_from_index, fetch_gdelt, fetch_openalex, fetch_rss,
)
from bluepulse_backend.ingestion.processing import process_source_article
from bluepulse_backend.ingestion.llm import ModelConfig
from bluepulse_backend.models import Article, Base, Source


RSS = b'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Police1</title>
<item><title>Police test drone mapping</title>
<link>https://www.police1.com/technology/articles/drone-mapping</link>
<description>Officers plan a drone mapping trial.</description>
<pubDate>Mon, 05 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>'''
DETAIL = '<main><article><h1>Police test drone mapping</h1>' + (
    '<p>Officers used drone mapping to document traffic collision scenes and compared the workflow with manual mapping.</p>' * 5
) + '<aside><p>Unrelated recommendation should not enter the article.</p></aside></article></main>'


class SourceQualityTests(unittest.TestCase):
    def test_previously_processed_title_only_article_is_hidden(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as session, session.begin():
            source = Source(slug="gdelt", name="GDELT", adapter="gdelt",
                            base_url="https://api.gdeltproject.org/api/v2/doc/doc")
            session.add(source)
            session.flush()
            session.add(Article(source_id=source.id, source_url="https://example.org/story",
                                canonical_url="https://example.org/story", source_title="Police AI",
                                processing_status="processed", parse_status="metadata_only"))
            session.flush()
            self.assertEqual(list(session.scalars(select(Article).where(*public_article_conditions()))), [])
        engine.dispose()

    def source(self) -> Source:
        return Source(
            slug="police1-recent", name="Police1", adapter="rss",
            base_url="https://www.police1.com/recently-published.rss", language="en",
            config={"allowed_hosts": ["www.police1.com"], "fetch_article_html": True,
                    "max_detail_pages": 2, "request_delay_seconds": 1},
        )

    def test_rss_fetches_allowed_detail_and_keeps_feed_date(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html"})

        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text", return_value=RSS):
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                articles = fetch_rss(self.source(), detail_client=client, sleeper=lambda _: None)
        self.assertEqual(articles[0].parse_status, "full_text")
        self.assertIn("traffic collision scenes", articles[0].body)
        self.assertNotIn("Unrelated recommendation", articles[0].body)
        self.assertEqual(articles[0].published_at.isoformat(), "2026-10-05T08:00:00+00:00")
        self.assertEqual(len(requested), 2)

    def test_rss_challenge_or_known_url_keeps_summary(self) -> None:
        url = "https://www.police1.com/technology/articles/drone-mapping"
        requests: list[str] = []

        def challenge(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(202, headers={"x-amzn-waf-action": "challenge"})

        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text", return_value=RSS):
            with httpx.Client(transport=httpx.MockTransport(challenge)) as client:
                fallback = fetch_rss(self.source(), detail_client=client, sleeper=lambda _: None)
                self.assertEqual(fallback[0].parse_status, "summary_only")
                requests.clear()
                known = fetch_rss(self.source(), known_urls={url}, detail_client=client,
                                  sleeper=lambda _: None)
        self.assertEqual(known[0].parse_status, "summary_only")
        self.assertEqual(requests, [])

    def test_html_challenge_is_not_silently_accepted_as_empty_feed(self) -> None:
        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text",
                   return_value=b"<html><title>Verify you are human</title></html>"):
            with self.assertRaises(SourceAccessChallenge):
                fetch_rss(self.source())

    def test_rss_topic_feed_filters_events_external_hosts_and_old_items(self) -> None:
        rss = b'''<rss version="2.0"><channel><title>NIST</title>
        <item><title>Police AI research</title>
        <link>https://www.nist.gov/news-events/news/2026/09/police-ai</link>
        <description>Police apply AI to investigations.</description>
        <pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate></item>
        <item><title>Future AI event</title>
        <link>https://www.nist.gov/news-events/events/2026/11/ai</link>
        <pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate></item>
        <item><title>External news</title>
        <link>https://example.org/news-events/news/2026/09/ai</link>
        <pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate></item>
        <item><title>Old research</title>
        <link>https://www.nist.gov/news-events/news/2020/01/old</link>
        <pubDate>Wed, 01 Jan 2020 12:00:00 GMT</pubDate></item>
        </channel></rss>'''
        source = Source(
            slug="nist", name="NIST", adapter="rss",
            base_url="https://www.nist.gov/news-events/Public%20safety/rss.xml",
            config={"allowed_hosts": ["www.nist.gov"],
                    "allowed_entry_hosts": ["www.nist.gov"],
                    "allowed_entry_paths": ["/news-events/news/"],
                    "max_age_days": 180},
        )
        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text", return_value=rss):
            items = fetch_rss(source, now=datetime(2026, 10, 5, tzinfo=UTC))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].parse_status, "summary_only")

    def test_gdelt_discovery_date_is_not_publication_date_and_title_waits(self) -> None:
        source = Source(
            slug="gdelt-public-news", name="GDELT", adapter="gdelt",
            base_url="https://api.gdeltproject.org/api/v2/doc/doc",
            config={"allowed_hosts": ["api.gdeltproject.org"], "query": "police drone"},
        )
        payload = {"articles": [{"url": "https://news.example/item", "title": "Police drone trial",
                                "seendate": "20261005T080000Z", "language": "Chinese",
                                "sourcecountry": "United States"}]}
        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text",
                   return_value=json.dumps(payload).encode()):
            item = fetch_gdelt(source)[0]
        self.assertIsNone(item.published_at)
        self.assertEqual(item.parse_status, "metadata_only")
        self.assertEqual(item.language, "zh")
        self.assertEqual(item.country_code, "US")
        with patch("bluepulse_backend.ingestion.processing.analyze_source_article") as model:
            result = process_source_article(item, source, ModelConfig("x", "x", "x"))
        self.assertEqual(result.processing_status, "pending_model")
        model.assert_not_called()

    def test_gdelt_only_fetches_configured_article_host_and_path(self) -> None:
        source = Source(
            slug="gdelt-public-news", name="GDELT", adapter="gdelt",
            base_url="https://api.gdeltproject.org/api/v2/doc/doc",
            config={"allowed_hosts": ["api.gdeltproject.org"], "query": "police drone",
                    "article_hosts": {"nij.ojp.gov": ["/topics/articles/"]},
                    "max_detail_pages": 2, "request_delay_seconds": 1},
        )
        allowed = "https://nij.ojp.gov/topics/articles/police-drone"
        outside = "https://example.org/police-drone"
        payload = {"articles": [{"url": allowed, "title": "Police drone study"},
                                {"url": outside, "title": "Police drone report"}]}
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(200, text=(
                '<meta property="article:published_time" content="2026-10-02T10:00:00Z">' + DETAIL
            ), headers={"content-type": "text/html"})

        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text",
                   return_value=json.dumps(payload).encode()):
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                items = fetch_gdelt(source, detail_client=client, sleeper=lambda _: None)
        self.assertEqual(items[0].parse_status, "full_text")
        self.assertEqual(items[0].published_at.isoformat(), "2026-10-02T10:00:00+00:00")
        self.assertEqual(items[1].parse_status, "metadata_only")
        self.assertEqual(requested, ["https://nij.ojp.gov/robots.txt", allowed])

    def test_openalex_abstract_index_ignores_unbounded_positions(self) -> None:
        self.assertEqual(_abstract_from_index({"study": [1], "police": [0], "bad": [10**9]}),
                         "police study")

    def test_openalex_uses_abstract_and_author_without_guessing_article_region(self) -> None:
        source = Source(
            slug="openalex-policing-tech", name="OpenAlex", adapter="openalex",
            base_url="https://api.openalex.org/works",
            config={"allowed_hosts": ["api.openalex.org"], "search": "policing technology"},
        )
        payload = {"results": [{"id": "https://openalex.org/W123", "title": "Police drone study",
                                "publication_date": "2026-10-01",
                                "abstract_inverted_index": {"Police": [0], "drones": [1], "studied": [2]},
                                "authorships": [{"author": {"display_name": "A. Researcher"},
                                                 "institutions": [{"country_code": "US"}]}]},
                               {"id": "https://openalex.org/W124", "title": "Collaborative school improvement",
                                "abstract_inverted_index": {"committee": list(range(150)),
                                                            "police": [151], "algorithm": [152]}}]}
        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text",
                   return_value=json.dumps(payload).encode()):
            items = fetch_openalex(source)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.body, "Police drones studied")
        self.assertEqual(item.parse_status, "abstract_only")
        self.assertEqual(item.author, "A. Researcher")
        self.assertIsNone(item.country_code)


if __name__ == "__main__":
    unittest.main()
