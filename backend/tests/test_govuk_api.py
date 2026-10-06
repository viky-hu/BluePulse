from __future__ import annotations

import unittest
from datetime import UTC, datetime

import httpx

from bluepulse_backend.ingestion.adapters import SourceRateLimited
from bluepulse_backend.ingestion.govuk_api import fetch_govuk_api
from bluepulse_backend.models import Source


NOW = datetime(2026, 10, 5, tzinfo=UTC)
AI_PATH = "/government/publications/police-use-of-artificial-intelligence-ai-factsheet"
DRONE_PATH = "/government/news/police-drone-trial"


def source() -> Source:
    return Source(
        slug="govuk-policing-tech", name="GOV.UK", adapter="govuk_api",
        base_url="https://www.gov.uk/api/search.json", language="en",
        config={"allowed_hosts": ["www.gov.uk"],
                "queries": ["police AI", "police drone"],
                "recent_days": 180, "count_per_query": 10,
                "max_content_pages": 3, "request_delay_seconds": 0.2},
    )


class GovUkApiTests(unittest.TestCase):
    def test_search_and_content_keep_real_date_and_avoid_attachment_only_full_text(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/api/search.json":
                self.assertEqual(request.url.params["filter_organisations"], "home-office")
                self.assertEqual(request.url.params["filter_public_timestamp"], "from:2026-04-08")
                return httpx.Response(200, json={"results": [
                    {"link": AI_PATH, "title": "Police use of artificial intelligence",
                     "description": "Home Office policy for police AI.",
                     "public_timestamp": "2026-09-01T00:00:00Z"},
                    {"link": DRONE_PATH, "title": "Police test drone mapping",
                     "description": "Officers will use drone technology.",
                     "public_timestamp": "2026-08-01T00:00:00Z"},
                    {"link": "/government/news/police-guns", "title": "Police firearms policy",
                     "description": "Routine procurement of ammunition.",
                     "public_timestamp": "2026-08-01T00:00:00Z"},
                    {"link": "https://bad.example/government/news/police-ai",
                     "title": "Police AI", "public_timestamp": "2026-09-01T00:00:00Z"},
                ]})
            if request.url.path == "/api/content" + AI_PATH:
                return httpx.Response(200, json={
                    "title": "Police use of artificial intelligence (AI): factsheet",
                    "description": "Police AI policy.",
                    "first_published_at": "2026-06-09T00:01:00+01:00",
                    "details": {"body": "<p>Police use artificial intelligence for investigation.</p>",
                                "attachments": [{"title": "Factsheet PDF"}]},
                })
            if request.url.path == "/api/content" + DRONE_PATH:
                return httpx.Response(200, json={
                    "title": "Police test drone mapping",
                    "first_published_at": "2026-07-31T12:00:00Z",
                    "details": {"body": (
                        "<figure><img src='https://assets.publishing.service.gov.uk/media/drone.jpg' "
                        "alt='Drone mapping'><figcaption>Trial image</figcaption></figure>"
                        + "<p>Police use drones for scene mapping.</p>" * 24
                    ), "images": [{"url": "https://evil.example/track.jpg"}]},
                })
            return httpx.Response(404, json={})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            diagnostics: dict[str, int] = {}
            articles = fetch_govuk_api(source(), diagnostics=diagnostics, client=client,
                                       sleeper=lambda _: None, now=NOW)
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].parse_status, "summary_only")
        self.assertEqual(articles[0].published_at.isoformat(), "2026-06-08T23:01:00+00:00")
        self.assertEqual(articles[1].parse_status, "full_text")
        self.assertEqual(len(articles[1].media), 1)
        self.assertEqual(articles[1].media[0].alt_text, "Drone mapping")
        self.assertEqual(articles[1].media[0].caption, "Trial image")
        self.assertEqual(diagnostics["relevant_candidates"], 2)
        self.assertEqual(diagnostics["content_pages"], 2)
        self.assertEqual(len(requested), 4)

    def test_known_article_skips_content_request(self) -> None:
        paths: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"results": [{
                "link": AI_PATH, "title": "Police AI factsheet",
                "description": "Police use of artificial intelligence",
                "public_timestamp": "2026-09-01T00:00:00Z",
            }]})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            articles = fetch_govuk_api(
                source(), known_urls={"https://www.gov.uk" + AI_PATH},
                client=client, sleeper=lambda _: None, now=NOW,
            )
        self.assertEqual(articles, [])
        self.assertEqual(paths, ["/api/search.json", "/api/search.json"])

    def test_detail_rate_limit_propagates(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/search.json":
                return httpx.Response(200, json={"results": [{
                    "link": AI_PATH, "title": "Police AI factsheet",
                    "description": "Police use of artificial intelligence",
                    "public_timestamp": "2026-09-01T00:00:00Z",
                }]})
            return httpx.Response(429, json={})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(SourceRateLimited):
                fetch_govuk_api(source(), client=client, sleeper=lambda _: None, now=NOW)

    def test_recent_index_update_of_old_article_is_filtered_without_partial_failure(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/search.json":
                return httpx.Response(200, json={"results": [{
                    "link": AI_PATH, "title": "Police AI factsheet",
                    "description": "Police use of artificial intelligence",
                    "public_timestamp": "2026-09-01T00:00:00Z",
                }]})
            return httpx.Response(200, json={
                "title": "Police AI factsheet", "first_published_at": "2020-01-01T00:00:00Z",
                "details": {"body": "<p>Police AI guidance.</p>"},
            })

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            diagnostics: dict[str, int] = {}
            articles = fetch_govuk_api(source(), diagnostics=diagnostics, client=client,
                                       sleeper=lambda _: None, now=NOW)
        self.assertEqual(articles, [])
        self.assertEqual(diagnostics["stale_content"], 1)
        self.assertEqual(diagnostics["detail_parse_failed"], 0)


if __name__ == "__main__":
    unittest.main()
