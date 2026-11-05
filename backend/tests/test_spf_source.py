from __future__ import annotations

from datetime import date

import httpx

from bluepulse_backend.live_sources import BoundedHTTP
from bluepulse_backend.source_collection import SOURCES, build_adapter
from bluepulse_backend.spf_source import HOST, LISTING, SpfPoliceLifeAdapter


OLD = "https://www.police.gov.sg/Media-Hub/Police-Life/2026/10/Old-Blockchain-Story"
NEW = "https://www.police.gov.sg/Media-Hub/Police-Life/2026/10/New-Cyber-Police-Story"


def test_latest_listing_precedes_carousel_and_body_excludes_related_links():
    listing = ("<div class='card-carousel'><a href='" + OLD + "'>Old Blockchain Story</a></div>"
               "<div class='latest-articles__listing'>"
               "<a href='" + NEW + "'>New Cyber Police Story</a>"
               "<a href='" + OLD + "'>Old Blockchain Story</a></div>")
    repeated = "<p>They checked technical findings with investigators before taking action.</p>" * 3
    article = ("<meta name='description' content='Digital police work'>"
               "<div class='lp-banner__text'><div class='h1'>New Cyber Police Story</div></div>"
               "<div class='published-date'>27 Oct 2026</div>"
               "<div class='content-block--custom-max-width'>"
               "<div class='rte'><p>Officers investigated digital evidence and traced criminal infrastructure.</p></div>"
               "<figure>Photo credit</figure>"
               "<div class='rte'>" + repeated +
               "<h3>Cyber Command Series</h3><p>Related article link</p></div></div>")
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /sitecore\n")
        if str(request.url) == LISTING:
            return httpx.Response(200, text=listing)
        if str(request.url) == NEW:
            return httpx.Response(200, text=article)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = build_adapter(SOURCES["spf-police-life"], client, max_items=1)
        adapter.http.delay_seconds = 0
        adapter.sleeper = lambda _: None
        rows = adapter.candidates()
    assert requested == [f"https://{HOST}/robots.txt", LISTING, NEW]
    assert adapter.diagnostics["listing_links"] == 2
    assert len(rows) == 1 and rows[0].published_date == date(2026, 10, 27)
    assert rows[0].published_at is None and "technical findings" in rows[0].body
    assert "Related article link" not in rows[0].body and "Photo credit" not in rows[0].body


def test_robots_disallow_stops_before_listing():
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /Media-Hub/\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = SpfPoliceLifeAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                       max_items=1, sleeper=lambda _: None)
        try:
            adapter.candidates()
        except Exception as exc:
            assert getattr(exc, "code", None) == "robots_disallowed_or_delayed"
        else:
            assert False, "robots disallow must stop collection"
    assert requested == ["/robots.txt"]
