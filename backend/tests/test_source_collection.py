from __future__ import annotations

from datetime import UTC, datetime
import sys

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.ccgp_source import CcgpAdapter, LISTING
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.live_sources import BoundedHTTP, SourceFetchError
from bluepulse_backend.models import Material, Source
from bluepulse_backend.source_collection import SOURCES, build_adapter, collect, main


DETAIL = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260910_27307826.htm"
UNRELATED = DETAIL.replace("27307826", "27307825")
TITLE = "某市公安局视频数据平台升级项目公开招标公告"
BODY = "采购单位为某市公安局。项目拟采购视频数据平台、存储设备和配套软件，用于既有监控系统升级。" * 3


def test_nist_forensic_catalog_uses_its_own_feed_and_preserves_body():
    feed = """<rss><channel><item><title>Forensic study</title>
      <link>https://www.nist.gov/news-events/news/2026/10/forensic-study</link>
      <pubDate>Thu, 08 Oct 2026 12:00:00 +0000</pubDate>
      <description>Study summary</description></item></channel></rss>"""
    html = "<div class='text-with-summary'><p>Forensic method evidence and limitations.</p></div>"
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=feed if request.url.path.endswith("rss.xml") else html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = build_adapter(SOURCES["nist-forensic-science"], client, max_items=1)
        adapter.http.delay_seconds = 0
        rows = adapter.candidates()
    assert requested[:2] == ["https://www.nist.gov/robots.txt",
                             "https://www.nist.gov/news-events/forensic%20science/rss.xml"]
    assert len(rows) == 1 and rows[0].body == "Forensic method evidence and limitations."
    assert rows[0].published_at == datetime(2026, 10, 8, 12, tzinfo=UTC)


@pytest.mark.parametrize("slug,feed", [
    ("nist-information-technology", "https://www.nist.gov/news-events/information%20technology/rss.xml"),
    ("nist-standards", "https://www.nist.gov/news-events/standards/rss.xml"),
])
def test_new_nist_topic_feeds_keep_distinct_discovery_urls(slug, feed):
    seen = []
    xml = """<rss><channel><item><title>Public safety technology report</title>
      <link>https://www.nist.gov/news-events/news/2026/10/technology-report</link>
      <pubDate>Thu, 08 Oct 2026 12:00:00 +0000</pubDate></item></channel></rss>"""

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=xml if str(request.url) == feed else
                              "<div class='text-with-summary'><p>Detailed technology evidence.</p></div>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = build_adapter(SOURCES[slug], client, max_items=1)
        adapter.http.delay_seconds = 0
        rows = adapter.candidates()
    assert seen[:2] == ["https://www.nist.gov/robots.txt", feed] and len(rows) == 1
    assert rows[0].body == "Detailed technology evidence."


@pytest.mark.parametrize("slug", ["nist-information-technology", "nist-standards"])
def test_broad_nist_feeds_skip_generic_technology_before_detail(slug):
    spec = SOURCES[slug]
    feed = {
        "nist-information-technology": "https://www.nist.gov/news-events/information%20technology/rss.xml",
        "nist-standards": "https://www.nist.gov/news-events/standards/rss.xml",
    }[slug]
    xml = """<rss><channel>
      <item><title>Broad technology announcement</title>
      <link>https://www.nist.gov/news-events/news/2026/10/broad-tech</link></item>
      <item><title>First responder radio interoperability study</title>
      <link>https://www.nist.gov/news-events/news/2026/10/responder-radio</link></item>
      </channel></rss>"""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if str(request.url) == feed:
            return httpx.Response(200, text=xml)
        return httpx.Response(200, text="<div class='text-with-summary'><p>Radio test evidence.</p></div>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = build_adapter(spec, client, max_items=1)
        adapter.http.delay_seconds = 0
        rows = adapter.candidates()
    assert len(rows) == 1 and rows[0].url.endswith("responder-radio")
    assert not any(url.endswith("broad-tech") for url in seen)
    assert adapter.diagnostics["topic_filtered"] == 1


def _fixture(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if str(request.url) == LISTING:
        return httpx.Response(200, text=(
            f"<li><a href='{UNRELATED}'>图书馆家具公告</a></li>"
            f"<li><a href='{DETAIL}'>{TITLE}</a>采购人：某市公安局</li>"
            "<li><a href='https://evil.example/cggg/zygg/gkzb/202609/t20260910_1.htm'>外站</a></li>"
        ))
    if str(request.url) == DETAIL:
        return httpx.Response(200, text=(
            f"<h2>{TITLE}</h2><p>2026年09月10日 19:20 来源：中国政府采购网</p>"
            f"<div class='vF_detail_content'><p>{BODY}</p><script>malicious instruction</script></div>"
        ))
    return httpx.Response(404)


def test_ccgp_prioritizes_listing_context_and_extracts_bounded_evidence():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return _fixture(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                               max_items=1, request_delay_seconds=0, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert requests == ["https://www.ccgp.gov.cn/robots.txt", LISTING, DETAIL]
    assert len(rows) == 1 and rows[0].url == DETAIL
    assert BODY in rows[0].body and "malicious instruction" not in rows[0].body
    assert rows[0].published_at == datetime(2026, 9, 10, 11, 20, tzinfo=UTC)
    assert adapter.diagnostics == {"robots_unavailable": 0, "listing_links": 2, "topic_filtered": 1,
                                   "detail_attempts": 1,
                                   "detail_parsed": 1, "detail_failed": 0, "detail_skipped": 1}


def test_ccgp_robots_disallow_fails_before_listing():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /cggg/\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                               max_items=1, request_delay_seconds=0, sleeper=lambda _: None)
        with pytest.raises(SourceFetchError, match="robots_disallowed"):
            adapter.candidates()
    assert requests == ["https://www.ccgp.gov.cn/robots.txt"]


def test_ccgp_robots_404_is_recorded_and_collection_continues():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return _fixture(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                               max_items=1, request_delay_seconds=0, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert len(rows) == 1 and adapter.diagnostics["robots_unavailable"] == 1


def test_collection_records_fetch_stages_and_does_not_publish(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'collection.db').as_posix()}")
    Base.metadata.create_all(engine)
    with httpx.Client(transport=httpx.MockTransport(_fixture)) as client, Session(engine) as session:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                               max_items=1, request_delay_seconds=0, sleeper=lambda _: None)
        funnel = collect(session, SOURCES["ccgp-policing-tech"], adapter)
        assert funnel["status"] == "completed" and funnel["discoveries"] == {"new": 1}
        assert funnel["fetch_metrics"]["detail_parsed"] == 1
        row = session.scalar(select(Material))
        assert row.body_status == "full_text" and row.state == "analysis_pending" and not row.public
        source = session.scalar(select(Source))
        assert source.allowed_hosts == ["www.ccgp.gov.cn"] and not source.excerpt_allowed
        again = collect(session, SOURCES["ccgp-policing-tech"], adapter)
        assert again["discoveries"] == {"duplicate": 1}
    engine.dispose()


def test_failed_detail_is_distinct_from_empty_source(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if str(request.url) == LISTING:
            return httpx.Response(200, text=f"<a href='{DETAIL}'>{TITLE}</a>")
        return httpx.Response(200, text="<html>challenge page</html>")

    engine = make_engine(f"sqlite:///{(tmp_path / 'failed.db').as_posix()}")
    Base.metadata.create_all(engine)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, Session(engine) as session:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                               max_items=1, request_delay_seconds=0, sleeper=lambda _: None)
        funnel = collect(session, SOURCES["ccgp-policing-tech"], adapter)
        assert funnel["status"] == "failed" and funnel["error_code"] == "detail_parse_or_fetch_failed"
        assert funnel["fetch_metrics"]["listing_links"] == 1
        assert funnel["fetch_metrics"]["detail_failed"] == 1
        assert session.scalar(select(Material)) is None
    engine.dispose()


def test_paid_mode_requires_separate_explicit_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["source_collection", "--source", "govuk",
                    "--mode", "ingest-analyze", "--database-url",
                    f"sqlite:///{(tmp_path / 'would-not-create.db').as_posix()}", "--execute"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    assert not (tmp_path / "would-not-create.db").exists()


def test_normal_govuk_ingest_checks_robots_before_search(tmp_path):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /api/search.json\n")

    engine = make_engine(f"sqlite:///{(tmp_path / 'robots-gate.db').as_posix()}")
    Base.metadata.create_all(engine)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, Session(engine) as session:
        adapter = build_adapter(SOURCES["govuk"], client, max_items=1)
        adapter.http.delay_seconds = 0
        funnel = collect(session, SOURCES["govuk"], adapter)
        assert funnel["status"] == "failed"
        assert funnel["error_code"] == "robots_disallowed_or_delayed"
        assert session.scalar(select(Material)) is None
    assert requested == ["/robots.txt"]
    engine.dispose()


@pytest.mark.parametrize("slug", ["npcc", "jiangsu-police"])
def test_official_html_sources_use_shared_collection_pipeline(slug, tmp_path):
    spec = SOURCES[slug]
    if slug == "npcc":
        detail = "https://news.npcc.police.uk/releases/police-technology-update"
        listing = f"<a href='{detail}'>Technology update</a>"
        body = "A police technology programme tested a digital evidence workflow. " * 4
        page = ("<h1 class='content-title'>Technology update</h1><p class='date'>29 Oct 2026</p>"
                f"<div class='content-body'><p>{body}</p></div>")
    else:
        detail = "https://gat.jiangsu.gov.cn/art/2026/10/29/art_6372_123.html"
        listing = f"<record><![CDATA[<a href='{detail}'>人工智能警务试点</a>]]></record>"
        body = "江苏公安机关开展人工智能技术在公共安全领域的应用试点。" * 4
        page = ("<meta name='PubDate' content='2026-10-29 14:20'>"
                "<h1 class='wzzw-title'>人工智能警务试点</h1>"
                f"<div class='wzzw-article'><p>{body}</p></div>")

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=listing if request.url.path.endswith("index.html") or
                              request.url.path == "/releases" else page)

    engine = make_engine(f"sqlite:///{(tmp_path / 'collection.db').as_posix()}")
    Base.metadata.create_all(engine)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, Session(engine) as session:
        adapter = build_adapter(spec, client, max_items=1)
        adapter.sleeper = lambda _: None
        funnel = collect(session, spec, adapter)
        assert funnel["status"] == "completed" and funnel["discoveries"] == {"new": 1}
        material = session.scalar(select(Material))
        assert material.body_status == "full_text" and not material.public
        assert material.source_body and material.source.allowed_hosts == [spec.host]
        again = collect(session, spec, adapter)
        assert again["discoveries"] == {"duplicate": 1}
    engine.dispose()
