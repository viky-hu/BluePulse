from datetime import date

import httpx
import pytest

from bluepulse_backend.ccgp_source import CcgpAdapter, HOST as CCGP_HOST
from bluepulse_backend.htx_source import HtxNewsAdapter, HOST as HTX_HOST
from bluepulse_backend.live_sources import BoundedHTTP, SourceFetchError
from bluepulse_backend.police_science_source import PoliceScienceAdapter, HOST as SCIENCE_HOST
from bluepulse_backend.source_expansion import BoundedHtmlSourceAdapter


def test_htx_listing_reads_reported_pages_without_requesting_articles():
    pages = []

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        assert request.url.path.endswith("/GetNewsAndEventsListing")
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(200, json={"totalItems": 3, "data": [
            {"articleType": "News", "url": f"/whats-happening/all-news---events/all-news/2026/test-{page}",
             "title": f"News {page}", "date": "28 October 2026"},
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = HtxNewsAdapter(BoundedHTTP(client, allowed_hosts={HTX_HOST}, delay_seconds=0),
                                 max_items=1, sleeper=lambda _: None)
        candidates = adapter.list_candidates()

    assert pages == [1, 2, 3]
    assert [(row.title, row.published_date, row.body) for row in candidates] == [
        (f"News {page}", date(2026, 10, 28), None) for page in (1, 2, 3)
    ]


@pytest.mark.parametrize("kind,host,listing_path,article_paths,listing", [
    ("pds", "pds.police.uk", "/welcome/blog/", ["/test-one/", "/test-two/"],
     "<h2 class='post-title'><a href='/test-one/'>One</a></h2>"
     "<h2 class='post-title'><a href='/test-two/'>Two</a></h2>"),
    ("ccgp", CCGP_HOST, "/cggg/zygg/gkzb/",
     ["/cggg/zygg/gkzb/202611/t20261101_111.htm", "/cggg/zygg/gkzb/202611/t20261102_222.htm"],
     "<li><a href='/cggg/zygg/gkzb/202611/t20261101_111.htm'>公安视频系统</a></li>"
     "<li><a href='/cggg/zygg/gkzb/202611/t20261102_222.htm'>公安通信系统</a></li>"),
    ("science", SCIENCE_HOST, "/sitemap.xml",
     ["/news-and-events/news/test-one/", "/news-and-events/news/test-two/"],
     "<urlset><url><loc>https://science.police.uk/news-and-events/news/test-one/</loc></url>"
     "<url><loc>https://science.police.uk/news-and-events/news/test-two/</loc></url></urlset>"),
])
def test_html_lists_are_uncapped_and_new_detail_workers_apply_robots(
    kind, host, listing_path, article_paths, listing,
):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=f"User-agent: *\nDisallow: {article_paths[1]}")
        assert request.url.path == listing_path
        return httpx.Response(200, text=listing)

    def adapter(client):
        http = BoundedHTTP(client, allowed_hosts={host}, delay_seconds=0)
        options = {"max_items": 1, "sleeper": lambda _: None}
        if kind == "pds":
            return BoundedHtmlSourceAdapter(http, kind=kind, **options)
        if kind == "ccgp":
            return CcgpAdapter(http, **options)
        return PoliceScienceAdapter(http, **options)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        candidates = adapter(client).list_candidates()
        assert requested == ["/robots.txt", listing_path]
        assert [item.url for item in candidates] == [f"https://{host}{path}" for path in article_paths]
        assert all(item.body is None for item in candidates)
        if kind == "science":
            assert all(item.title == "" for item in candidates)
        with pytest.raises(SourceFetchError, match="robots_disallowed"):
            adapter(client).fetch_detail(candidates[1])

    assert requested == ["/robots.txt", listing_path, "/robots.txt"]
