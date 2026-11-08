from datetime import UTC, datetime

import httpx

from bluepulse_backend.live_sources import BoundedHTTP, GovUkAdapter, NistRssAdapter


def test_govuk_pagination_only_reads_listings_until_detail_is_requested():
    paths = ["/government/news/first", "/government/news/second", "/government/news/third"]
    requests = []

    def fetch(request):
        requests.append(request.url)
        if request.url.path == "/api/search.json":
            start = int(request.url.params.get("start", 0))
            indexes = (0, 1) if start == 0 else (2,)
            return httpx.Response(200, json={"total": 3, "results": [
                {"link": paths[index], "title": f"List {index}", "description": "Listing summary",
                 "public_timestamp": "2026-11-08T08:00:00Z"} for index in indexes
            ]})
        return httpx.Response(200, json={"title": "Detail heading", "details": {"body": "<p>Body evidence</p>"}})

    with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0), max_items=1)
        listed = adapter.list_candidates()
        assert [httpx.URL(item.url).path for item in listed] == paths
        assert all(item.body is None for item in listed)
        assert [url.params.get("start", "0") for url in requests] == ["0", "2"]
        fetched = adapter.fetch_detail(listed[2])
    assert [url.path for url in requests] == ["/api/search.json", "/api/search.json", "/api/content" + paths[2]]
    assert fetched.title == "Detail heading"
    assert fetched.body == "Body evidence"
    assert fetched.published_at == datetime(2026, 11, 8, 8, tzinfo=UTC)


def test_govuk_can_resume_a_list_page_at_the_saved_offset():
    def fetch(request):
        assert request.url.path == "/api/search.json"
        assert request.url.params["start"] == "30"
        return httpx.Response(200, json={"start": 30, "total": 31, "results": [
            {"link": "/government/news/latest"}
        ]})

    with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0))
        pages = list(adapter.iter_listing_pages(start=30))
    assert len(pages) == 1 and pages[0][1] is None
    assert pages[0][0][0].url == "https://www.gov.uk/government/news/latest"
    assert pages[0][0][0].title == ""


def test_nist_lists_beyond_diagnostic_limit_without_reading_body_pages():
    urls = [f"https://www.nist.gov/news-events/news/{index}" for index in range(4)]
    rss = "<rss><channel>" + "".join(
        f"<item><title>Police update {index}</title><link>{url}</link></item>"
        for index, url in enumerate(urls)
    ) + "</channel></rss>"
    requests = []

    def fetch(request):
        requests.append(str(request.url))
        if request.url.path.endswith("/rss.xml"):
            return httpx.Response(200, text=rss)
        return httpx.Response(200, text='<div class="text-with-summary"><p>Documented test body.</p></div>')

    with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
        adapter = NistRssAdapter(BoundedHTTP(client, allowed_hosts={"www.nist.gov"}, delay_seconds=0), max_items=2)
        listed = adapter.list_candidates()
        assert [item.url for item in listed] == urls
        assert all(item.body is None for item in listed)
        assert requests == [adapter.feed]
        fetched = adapter.fetch_detail(listed[3])
        assert fetched.body == "Documented test body."
        assert requests[-1] == urls[3]
        assert [item.url for item in adapter.candidates()] == urls[:2]
