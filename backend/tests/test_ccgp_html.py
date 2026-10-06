from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bluepulse_backend.api import article_detail
from bluepulse_backend.ingestion.ccgp_html import fetch_ccgp_html
from bluepulse_backend.ingestion.llm import ModelAnalysisError, ModelConfig, NoticeAnalysis, _parse_analysis
from bluepulse_backend.ingestion.pipeline import _article_from_item, _topic_slugs
from bluepulse_backend.models import Base, Source, Topic

LISTING_URL = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/"
DETAIL_URL = "https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260910_27307826.htm"
TITLE = "某市公安局视频监控系统升级项目公开招标公告"
LISTING_HTML = f"<html><ul><li><a href='{DETAIL_URL}'>{TITLE}</a></li></ul></html>"
DETAIL_HTML = (
    f"<html><h2>{TITLE}</h2><p>2026年09月10日 19:20 来源：中国政府采购网</p>"
    "<div class='vF_detail_content'>采购单位为某市公安局。项目采购公共安全视频监控设备、"
    "视频数据平台和存储系统，用于现有监控点位升级。预算金额为人民币四百万元。"
    "采购需求要求设备与现有网络系统兼容，并提供部署、调试和技术支持服务。"
    "项目还包括平台软件升级、前端摄像机安装和后端数据存储能力扩展。"
    "本公告的具体招标文件和投标要求以采购人发布的正式文件为准。</div></html>"
)


def make_source() -> Source:
    return Source(
        id=uuid4(), slug="ccgp-policing-tech", name="中国政府采购网警务科技公告",
        base_url=LISTING_URL, adapter="ccgp_html", region="domestic", country_code="CN",
        language="zh", source_type="government", topics=["policing"],
        config={
            "allowed_hosts": ["www.ccgp.gov.cn"],
            "listing_urls": [LISTING_URL],
            "max_candidates": 3,
            "max_articles": 2,
            "request_delay_seconds": 1,
        },
    )


class CcgpHtmlTests(unittest.TestCase):
    def test_bad_detail_is_skipped_and_smoke_does_not_call_model(self) -> None:
        bad = DETAIL_URL.replace("27307826", "27307825")

        def respond(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if str(request.url) == LISTING_URL:
                return httpx.Response(200, text=(
                    f"<li><a href='{bad}'>公安智能视频公告</a></li>"
                    f"<li><a href='{DETAIL_URL}'>{TITLE}</a></li>"
                ))
            if str(request.url) == bad:
                return httpx.Response(200, text="<h1>公安智能视频公告</h1><div id='content'>too short</div>")
            return httpx.Response(200, text=DETAIL_HTML)

        stats: dict[str, int] = {}
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with patch("bluepulse_backend.ingestion.ccgp_html.load_model_config") as config:
                articles = fetch_ccgp_html(make_source(), client=client, sleeper=lambda _: None,
                                           diagnostics=stats, analyze=False)
        config.assert_not_called()
        self.assertEqual([article.url for article in articles], [DETAIL_URL])
        self.assertEqual(stats["detail_parse_failed"], 1)
        self.assertEqual(stats["model_calls"], 0)

    @staticmethod
    def _response(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if str(request.url) == LISTING_URL:
            return httpx.Response(200, text=LISTING_HTML)
        if str(request.url) == DETAIL_URL:
            return httpx.Response(200, text=DETAIL_HTML)
        return httpx.Response(404)

    def test_html_model_result_uses_existing_article_shape(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if str(request.url) == LISTING_URL:
                return httpx.Response(200, text=LISTING_HTML)
            if str(request.url) == DETAIL_URL:
                return httpx.Response(200, text=DETAIL_HTML)
            return httpx.Response(404)

        analysis = NoticeAnalysis(
            relevant=True, relevance=0.95, short_title="某市公安局升级视频监控系统",
            summary="某市公安局拟升级视频监控设备、数据平台和存储系统，预算四百万元。",
            topics=("policing", "public-safety-tech", "procurement-projects"),
            importance_score=72,
        )
        source = make_source()
        diagnostics: dict[str, int] = {}
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with patch("bluepulse_backend.ingestion.ccgp_html.load_model_config", return_value=ModelConfig("https://example.test/v1", "test", "test")):
                with patch("bluepulse_backend.ingestion.ccgp_html.analyze_notice", return_value=analysis) as model:
                    items = fetch_ccgp_html(
                        source, client=client, sleeper=lambda _: None, diagnostics=diagnostics,
                    )

        self.assertEqual(requested, ["https://www.ccgp.gov.cn/robots.txt", LISTING_URL, DETAIL_URL])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_at, datetime(2026, 9, 10, 11, 20, tzinfo=UTC))
        self.assertEqual(items[0].parse_status, "full_text")
        self.assertEqual(items[0].processing_status, "processed")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(diagnostics["listing_links"], 1)
        self.assertEqual(diagnostics["detail_pages"], 1)
        self.assertEqual(diagnostics["model_calls"], 1)
        self.assertEqual(diagnostics["keyword_filtered"], 0)
        article = _article_from_item(items[0], source)
        self.assertEqual(article.source_title, TITLE)
        self.assertEqual(article.zh_title, analysis.short_title)
        self.assertEqual(article.zh_summary, analysis.summary)
        self.assertEqual(article.source_url, DETAIL_URL)
        self.assertEqual(article.importance_score, 72)
        self.assertEqual(article.region, "domestic")
        self.assertEqual(_topic_slugs(items[0], source), list(analysis.topics))

        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session, session.begin():
            session.add(source)
            article.topics = [
                Topic(slug=slug, name_zh=slug, name_en=slug)
                for slug in analysis.topics
            ]
            session.add(article)
            session.flush()
            detail = article_detail(article.id, session)
            self.assertEqual(detail["title"], analysis.short_title)
            self.assertEqual(detail["source_title"], TITLE)
            self.assertEqual(detail["source_body"], items[0].body)
            self.assertEqual(detail["summary"], analysis.summary)
            self.assertEqual(detail["topics"], list(analysis.topics))
            self.assertEqual(detail["url"], DETAIL_URL)
        engine.dispose()

    def test_robots_disallow_stops_before_listing(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(200, text="User-agent: *\nDisallow: /cggg/\n")

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with patch("bluepulse_backend.ingestion.ccgp_html.load_model_config", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "robots.txt"):
                    fetch_ccgp_html(make_source(), client=client, sleeper=lambda _: None)
        self.assertEqual(requested, ["https://www.ccgp.gov.cn/robots.txt"])

    def test_known_article_skips_detail_and_model(self) -> None:
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(200, text=LISTING_HTML)

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with patch("bluepulse_backend.ingestion.ccgp_html.load_model_config", return_value=None):
                items = fetch_ccgp_html(
                    make_source(), known_urls={DETAIL_URL}, client=client, sleeper=lambda _: None,
                )
        self.assertEqual(items, [])
        self.assertEqual(requested, ["https://www.ccgp.gov.cn/robots.txt", LISTING_URL])

    def test_pagination_and_buyer_context_prioritize_relevant_notice(self) -> None:
        page_two = f"{LISTING_URL}index_1.htm"
        unrelated_url = DETAIL_URL.replace("27307826", "27307825")
        requested: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            requested.append(url)
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            if url == LISTING_URL:
                return httpx.Response(200, text=f"<li><a href='{unrelated_url}'>图书馆家具采购公告</a></li>")
            if url == page_two:
                return httpx.Response(
                    200,
                    text=f"<li><a href='{DETAIL_URL}'>智能视频监控设备采购公告</a>采购人：某市公安局</li>",
                )
            if url == DETAIL_URL:
                return httpx.Response(200, text=DETAIL_HTML)
            return httpx.Response(404)

        source = make_source()
        source.config = {**source.config, "max_listing_pages": 2, "max_candidates": 1}
        diagnostics: dict[str, int] = {}
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with patch("bluepulse_backend.ingestion.ccgp_html.load_model_config", return_value=None):
                articles = fetch_ccgp_html(
                    source, client=client, sleeper=lambda _: None, diagnostics=diagnostics,
                )
        self.assertEqual([article.url for article in articles], [DETAIL_URL])
        self.assertEqual(requested, ["https://www.ccgp.gov.cn/robots.txt", LISTING_URL, page_two, DETAIL_URL])
        self.assertEqual(diagnostics["listing_pages"], 2)
        self.assertEqual(diagnostics["listing_links"], 2)
        self.assertEqual(diagnostics["detail_pages"], 1)

    def test_model_output_rejects_bad_scores(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "评分"):
            _parse_analysis('{"relevant":true,"relevance":3,"short_title":"x","summary":"x","topics":[],"importance_score":1}')

    def test_model_rejects_irrelevant_notice(self) -> None:
        analysis = NoticeAnalysis(False, 0.1, "", "", (), 0)
        with httpx.Client(transport=httpx.MockTransport(self._response)) as client:
            with patch("bluepulse_backend.ingestion.ccgp_html.load_model_config", return_value=ModelConfig("https://example.test/v1", "test", "test")):
                with patch("bluepulse_backend.ingestion.ccgp_html.analyze_notice", return_value=analysis):
                    self.assertEqual(fetch_ccgp_html(make_source(), client=client, sleeper=lambda _: None), [])

    def test_model_failure_preserves_source_material(self) -> None:
        with httpx.Client(transport=httpx.MockTransport(self._response)) as client:
            with patch("bluepulse_backend.ingestion.ccgp_html.load_model_config", return_value=ModelConfig("https://example.test/v1", "test", "test")):
                with patch("bluepulse_backend.ingestion.ccgp_html.analyze_notice", side_effect=ModelAnalysisError("test")):
                    items = fetch_ccgp_html(make_source(), client=client, sleeper=lambda _: None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].processing_status, "model_failed")
        self.assertEqual(items[0].title, TITLE)
        self.assertIn("视频监控设备", items[0].body or "")


if __name__ == "__main__":
    unittest.main()
