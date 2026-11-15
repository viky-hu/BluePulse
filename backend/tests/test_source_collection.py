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
from bluepulse_backend.pipeline import Candidate
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


def test_ccgp_scheduled_listing_traverses_both_archives_and_parses_live_date_format():
    local = LISTING.replace("/zygg/", "/dfgg/")
    detail = local + "202611/t20261114_27686532.htm"
    vpn = local + "202611/t20261114_27686439.htm"
    requests = []

    def handler(request):
        url = str(request.url)
        requests.append(url)
        if url == local:
            return httpx.Response(200, text=(
                "<li><a href='./202611/t20261114_27686659.htm'>高校设备采购</a>"
                "发布时间：2026-11-14 19:38</li>"
                "<script>Pager({size: 2, current: 0, prefix: 'index', suffix: 'htm'})</script>"
            ))
        if url == local + "index_1.htm":
            return httpx.Response(200, text=(
                "<li><a href='./202611/t20261114_27686532.htm'>思南路99号音视频系统的公开招标公告</a>"
                "发布时间：2026-11-14 18:39 地域：上海 采购人：上海市公安局（主管）</li>"
                "<li><a href='./202611/t20261114_27686439.htm'>警务通VPN租赁服务项目</a>"
                "发布时间：2026-11-14 17:55 地域：浙江 采购人：绍兴市公安局越城区分局</li>"
            ))
        return _fixture(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                               request_delay_seconds=0)
        pages = list(adapter.iter_listing_pages())
    assert requests == ["https://www.ccgp.gov.cn/robots.txt", LISTING, local, local + "index_1.htm"]
    assert [checkpoint for _, checkpoint in pages] == [1, 2, None]
    assert [item.url for page, _ in pages for item in page] == [DETAIL, detail, vpn]
    assert pages[-1][0][0].published_at == datetime(2026, 11, 14, 10, 39, tzinfo=UTC)


def test_ccgp_official_award_entry_uses_raw_dates_and_preserves_day_precision():
    archive = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/"
    article = archive + "202611/t20261114_27686532.htm"
    markup = """
        <li><a href="./202611/t20261114_27686532.htm"
          title="公安局电子物证实验室建设中标结果公告">公安局电子物证…</a>
          发布时间：2026-11-14</li>
        <li><a href="./202611/t20261112_27686533.htm">高校窗帘</a>
          发布时间：2026年11月12日 17:00</li>
        <script>Pager({size:25, current:24, prefix:'index',suffix:'htm'});</script>
    """

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        assert str(request.url) == archive + "index_24.htm"
        return httpx.Response(200, text=markup)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                              request_delay_seconds=0)
        assert set(adapter.listing_entries) == {
            f"{authority}-{notice}" for authority in ("central", "local")
            for notice in ("tender", "award", "transaction", "correction", "consultation",
                           "negotiation", "termination", "other-notice", "inquiry")
        }
        [(rows, following)] = list(adapter.iter_entry_pages("local-award", start=24))
    assert following is None
    assert rows[0].url == article and rows[0].title == "公安局电子物证实验室建设中标结果公告"
    assert rows[0].published_at is None and rows[0].published_date.isoformat() == "2026-11-14"
    assert adapter.listing_page_evidence["oldest_at"] == datetime(2026, 11, 12, 9, tzinfo=UTC)
    assert adapter.listing_page_evidence["terminal"] == "truncated"


def test_ccgp_detail_uses_publication_header_before_procurement_event_dates():
    article = "https://www.ccgp.gov.cn/cggg/zygg/gzgg/202611/t20261114_27686532.htm"
    markup = ("<p>网页时间 2026-11-14 23:59</p><h2>公安局通信系统公告更正</h2>"
              "<p><span id='pubTime'>2026年11月14日 21:00</span></p>"
              "<div class='vF_detail_content'><p>采购文件更正，开标时间为2026-11-16 09:00。</p>"
              "<p>" + BODY + "</p></div>")

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        assert str(request.url) == article
        return httpx.Response(200, text=markup)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                              request_delay_seconds=0)
        row = adapter.fetch_detail(Candidate(url=article, title="更正公告"))
    assert row.published_at == datetime(2026, 11, 14, 13, tzinfo=UTC)
    assert "2026-11-16 09:00" in row.body


def test_ccgp_extracts_body_despite_unmatched_inline_markup():
    from bluepulse_backend.pipeline import Candidate

    html = ("<h2>原站成交公告</h2><span id='pubTime'>2026年11月13日 16:30</span>"
            "<div class='vF_detail_content'><div><p><br/><br></br></b></b>"
            + "中标结果及公告原文。" * 40 + "</p></div></div><footer>站点尾注</footer>")

    def respond(request):
        return httpx.Response(404 if request.url.path == '/robots.txt' else 200,
                              content=html.encode('utf-8'))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                              max_items=1)
        result = adapter.fetch_detail(Candidate(DETAIL, "列表标题"))
    assert result.body == "中标结果及公告原文。" * 40


def test_ccgp_detail_date_only_takes_precedence_over_a_listing_time():
    from bluepulse_backend.pipeline import Candidate

    html = f"<h2>{TITLE}</h2><span id='pubTime'>2026年9月10日</span><div class='vF_detail_content'>{BODY}</div>"

    def respond(request):
        return httpx.Response(404 if request.url.path == '/robots.txt' else 200, text=html)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                              max_items=1)
        result = adapter.fetch_detail(Candidate(DETAIL, TITLE, published_at=datetime(2026, 9, 10, 12, tzinfo=UTC)))
    assert result.published_at is None and result.published_date.isoformat() == "2026-09-10"


def test_ccgp_detail_keeps_scores_separate_from_adjacent_award_amounts():
    from bluepulse_backend.pipeline import Candidate

    raw = ("<div class='vF_detail_content'><p>中标结果及项目说明。"
           + "此处只含公告正文。" * 20 + "</p><table><tr>"
           "<td>91.92</td><td>4880000.00元</td><td>无</td></tr></table></div>")

    def respond(request):
        return httpx.Response(404 if request.url.path == '/robots.txt' else 200,
                              content=raw.encode('utf-8'))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                              max_items=1)
        result = adapter.fetch_detail(Candidate(DETAIL, "项目中标"))
    assert "91.92 | 4880000.00元 | 无" in result.body


def test_ccgp_distinguishes_original_notice_date_from_reprint_and_amended_tender_date():
    archive = "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202611/"
    article = archive + "t20261114_1.htm"
    another = archive + "t20261114_2.htm"
    title = "某公安局视音频数据采集设备采购更正公告"

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        local_header = f"<h2>{title}</h2><h3>发布日期：2026年11月4日</h3>" if str(request.url) == article else ""
        return httpx.Response(200, text=(f"<h2>{title}</h2><span id='pubTime'>2026年11月14日 00:15</span>"
            f"<div class='vF_detail_content'>{local_header}<h3>一、项目基本情况</h3>"
            f"<p>原公告发布日期：2026年10月29日</p><p>{BODY}</p></div>"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                              request_delay_seconds=0)
        syndicated = adapter.fetch_detail(Candidate(url=article, title=title))
        ordinary = adapter.fetch_detail(Candidate(url=another, title=title))
    reprint = datetime(2026, 11, 13, 16, 15, tzinfo=UTC)
    assert syndicated.published_at is None and syndicated.published_date.isoformat() == "2026-11-04"
    assert syndicated.source_updated_at == reprint
    assert ordinary.published_at == reprint and ordinary.source_updated_at is None


def test_ccgp_keeps_relevant_specialist_procurements_when_notice_title_omits_police():
    archive = "https://www.ccgp.gov.cn/cggg/dfgg/jzxcs/"
    titles = (
        ("山东出入境边防检查总站“境灵”AI建设平台服务项目", ""),
        ("刑侦总队采购液质联用仪等检案仪器维保服务", ""),
        ("成都市公安局电子卷宗制作设备采购项目", ""),
        ("荣昌区公安局采购远程指挥调度设备", ""),
        ("浙江五石关于AI辅助办案助手采购项目", ""),
        ("2026年执法单兵、派出所接处警车辆车载4G传输流量租赁", ""),
        ("颍东区路口信号灯和电子警察工程", ""),
        ("2026年消防装备采购项目", "采购人：某消防救援支队"),
        ("诉讼服务满意度评价终端采购项目", "采购人：某市人民法院"),
        ("智能应急救援辅助决策系统开发服务中标公告", "采购人：某院校"),
        ("液质联用仪采购项目", "采购人：某大学"),
        ("全校办公系统建设", "采购人：某大学"),
        ("派出所办公家具采购项目", ""),
    )
    page = "".join(
        f'<li><a href="./202611/t20261114_{index}.htm">{title}</a>'
        f'发布时间：2026-11-14 20:00 {context}</li>'
        for index, (title, context) in enumerate(titles)
    )

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        assert str(request.url) == archive
        return httpx.Response(200, text=page)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = CcgpAdapter(BoundedHTTP(client, allowed_hosts={"www.ccgp.gov.cn"}, delay_seconds=0),
                              request_delay_seconds=0)
        [(items, _)] = list(adapter.iter_entry_pages("local-consultation"))
    assert [item.title for item in items] == [title for title, _ in titles[:10]]


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
