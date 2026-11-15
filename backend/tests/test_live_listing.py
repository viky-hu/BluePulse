from datetime import UTC, datetime

import httpx
import pytest

from bluepulse_backend.live_sources import BoundedHTTP, GovUkAdapter, NistRssAdapter, SourceFetchError


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


def test_govuk_scheduled_entry_scans_all_home_office_updates_newest_first():
    def fetch(request):
        assert request.url.params["filter_organisations"] == "home-office"
        assert request.url.params["order"] == "-public_timestamp"
        assert "q" not in request.url.params
        return httpx.Response(200, json={"start": 0, "total": 1, "results": [
            {"link": "/government/news/report-on-police-digital-evidence",
             "title": "Report on police digital evidence", "public_timestamp": "2026-11-10T23:30:00Z"}
        ]})

    with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0))
        [(page, following)] = list(adapter.iter_entry_pages("default"))
    assert page[0].url.endswith("/report-on-police-digital-evidence") and following is None
    assert page[0].published_at is None
    assert page[0].source_updated_at == datetime(2026, 11, 10, 23, 30, tzinfo=UTC)
    assert adapter.listing_page_evidence["ordered"]
    assert adapter.listing_page_evidence["oldest_at"] == datetime(2026, 11, 10, 23, 30, tzinfo=UTC)


def test_govuk_distinguishes_a_future_statistics_release_from_an_article():
    from bluepulse_backend.pipeline import Candidate

    url = "https://www.gov.uk/government/statistics/announcements/police-workforce"
    detail = {"title": "Police workforce statistics", "document_type": "national_statistics_announcement",
              "first_published_at": "2026-11-10T23:30:00Z",
              "details": {"release_timestamp": "2999-01-27T09:30:00Z"}}
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=detail)
    )) as client, pytest.raises(SourceFetchError) as raised:
        adapter = GovUkAdapter(BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0))
        adapter.fetch_detail(Candidate(url=url, title=detail["title"]))
    assert raised.value.code == "statistics_not_yet_released"


def test_bounded_http_exposes_server_retry_after_for_worker():
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(429, headers={"Retry-After": "120"})
    )) as client, pytest.raises(SourceFetchError) as raised:
        BoundedHTTP(client, allowed_hosts={"www.gov.uk"}, delay_seconds=0).get("https://www.gov.uk")
    assert raised.value.code == "http_429" and raised.value.retry_after_seconds == 120


def test_nist_topic_evidence_does_not_treat_future_event_timestamps_as_news():
    path = "/news-events/news/2026/11/police-evidence-review"
    html = (f'<article about="{path}" class="nist-teaser"><h3 class="nist-teaser__title">'
            f'<a href="{path}">Police evidence review</a></h3>'
            '<time datetime="2026-11-13T12:00:00Z">November 13, 2026</time></article>')

    def fetch(request):
        if request.url.path.endswith("rss.xml"):
            return httpx.Response(200, text=("<rss><channel><item><title>Public safety workshop</title>"
                "<link>https://www.nist.gov/news-events/events/2027/workshop</link>"
                "<pubDate>Mon, 01 Feb 2027 12:00:00 GMT</pubDate></item>"
                f"<item><title>Police evidence review</title><link>https://www.nist.gov{path}</link>"
                "<pubDate>Fri, 13 Nov 2026 12:00:00 +0000\n - Fri, 18 Dec 2026 12:00:00 +0000</pubDate>"
                "</item></channel></rss>"))
        assert request.url.path == "/news-events/news-updates/topic/249421"
        return httpx.Response(200, text=html)

    with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
        adapter = NistRssAdapter(BoundedHTTP(client, allowed_hosts={"www.nist.gov"}, delay_seconds=0),
                                 topic_ids=("249421",))
        [(news, more)] = list(adapter.iter_entry_pages("news-249421"))
        assert news[0].published_at is None and news[0].published_date.isoformat() == "2026-11-13"
        assert more is None and adapter.listing_page_evidence["terminal"] == "exhausted"
        [(feed, more)] = list(adapter.iter_entry_pages("default"))
    assert more is None and len(feed) == 1 and feed[0].published_at is None
    assert feed[0].published_date.isoformat() == "2026-11-13"
    assert adapter.listing_page_evidence["oldest_at"].isoformat() == "2026-11-13"
    assert adapter.listing_page_evidence["terminal"] == "truncated"


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
