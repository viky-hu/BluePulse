from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx

from bluepulse_backend.ingestion.adapters import fetch_rss
from bluepulse_backend.models import Source

ROOT = Path(__file__).resolve().parents[1]
GOOD = "https://www.biometricupdate.com/202610/police-fingerprint-search"
RSS = f'''<rss version="2.0"><channel><title>Law Enforcement</title>
<item><title>Police fingerprint search uses contactless biometrics</title><link>{GOOD}</link>
<pubDate>Fri, 02 Oct 2026 15:27:04 GMT</pubDate>
<description>Police apply a contactless fingerprint search to missing-person cases.</description></item>
<item><title>External article</title><link>https://example.org/202610/external</link>
<pubDate>Fri, 02 Oct 2026 15:27:04 GMT</pubDate></item>
<item><title>Unrelated path</title><link>https://www.biometricupdate.com/wp-admin/private</link>
<pubDate>Fri, 02 Oct 2026 15:27:04 GMT</pubDate></item></channel></rss>'''.encode()
DETAIL = "<article><p>" + "Police use contactless fingerprint identification for missing people. " * 8 + "</p></article>"


class BiometricUpdateSourceTests(unittest.TestCase):
    def source(self) -> Source:
        rows = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
        row = next(row for row in rows if row["slug"] == "biometric-update-law-enforcement-rss")
        return Source(**row)

    def test_category_feed_filters_links_and_extracts_approved_detail(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(200, text=DETAIL, headers={"content-type": "text/html"})

        with patch("bluepulse_backend.ingestion.adapters._get_json_or_text", return_value=RSS):
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                articles = fetch_rss(self.source(), detail_client=client,
                                     sleeper=lambda _: None, now=datetime(2026, 10, 6, tzinfo=UTC))
        self.assertEqual([item.url for item in articles], [GOOD])
        self.assertEqual(articles[0].parse_status, "full_text")
        self.assertIn("fingerprint identification", articles[0].body)
        self.assertEqual(requested, ["https://www.biometricupdate.com/robots.txt", GOOD])


if __name__ == "__main__":
    unittest.main()
