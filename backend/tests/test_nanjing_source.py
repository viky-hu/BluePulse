from datetime import date, timedelta

import httpx
import pytest

from bluepulse_backend.live_sources import SourceFetchError
from bluepulse_backend.nanjing_source import LISTING
from bluepulse_backend.source_collection import SOURCE_REGISTRY, build_adapter


def test_nanjing_reads_official_pagination_and_detail_publication_time():
    calls = []
    body = "南京交管将路面预警接入指挥平台，试点期间记录了每次预警及现场处置。 " * 8

    def response(request):
        path = request.url.path
        calls.append(path)
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if path in ("/jwdt/", "/jwdt/index_1.html"):
            position = int(path.endswith("index_1.html"))
            day = 16 - position
            return httpx.Response(200, text=f"""
              <li><a href="./202611/t202611{day}_123.html" title="警务技术试点">试点</a><span>2026-11-{day}</span></li>
              <li><a href="https://outside.invalid/jwdt/202611/t20261116_123.html">无关</a></li>
              <script>createPageHTML(2, {position}, "index", "html")</script>""")
        return httpx.Response(200, text=f"""
          <div class="doctitle">南京警务技术试点</div>
          <div class="field_con1">责任编辑：南京市公安局 发布时间：2026-11-16 14:59</div>
          <div class="doccontent"><p>{body}</p></div><footer>无关页脚</footer>""")

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        adapter = build_adapter(SOURCE_REGISTRY["nanjing-police"], client, max_items=2)
        adapter.reader.sleeper = lambda _: None
        [(first, following), (second, last)] = list(adapter.iter_entry_pages("default"))
        detail = adapter.fetch_detail(first[0])
    assert calls == ["/robots.txt", "/jwdt/", "/jwdt/index_1.html", "/jwdt/202611/t20261116_123.html"]
    assert following == 1 and last is None and len(first) == len(second) == 1
    assert second[0].published_date == date(2026, 11, 15)
    assert detail.url.startswith(LISTING) and detail.published_at.hour == 14
    assert detail.published_at.utcoffset() == timedelta(hours=8)
    assert detail.title == "南京警务技术试点" and "无关页脚" not in detail.body


def test_nanjing_stops_when_listing_is_disallowed():
    def response(request):
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, text="User-agent: *\nDisallow: /jwdt/")

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        adapter = build_adapter(SOURCE_REGISTRY["nanjing-police"], client, max_items=2)
        with pytest.raises(SourceFetchError, match="robots_disallowed_or_delayed"):
            adapter.list_candidates()
