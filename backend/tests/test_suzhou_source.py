from datetime import date, timedelta

import httpx
import pytest

from bluepulse_backend.live_sources import SourceFetchError
from bluepulse_backend.source_collection import SOURCE_REGISTRY, build_adapter


SPEC = SOURCE_REGISTRY["suzhou-police"]


def test_suzhou_accepts_missing_file_redirect_and_reads_official_pages():
    calls = []
    body = "苏州公安用无人机热成像定位夜间落水人员，并将坐标同步给现场救援人员。" * 8

    def response(request):
        path = request.url.path
        calls.append(path)
        assert request.url.scheme == "https"
        if path == "/robots.txt":
            return httpx.Response(302, headers={"Location": "http://gonganju.suzhou.gov.cn"})
        if path in ("/gaj/jwdt/nav_list.shtml", "/gaj/jwdt/nav_list_2.shtml"):
            page = 2 if path.endswith("_2.shtml") else 1
            return httpx.Response(200, text=f"""
              <li><a href="./202611/{page:032x}.shtml">苏州警务技术</a><span>2026-11-{17-page}</span></li>
              <li><a href="https://other.invalid/gaj/jwdt/202611/{3:032x}.shtml">其他网站</a></li>
              <script>createPageHTML('page_div', 2, {page}, 'nav_list', 'shtml', 2);</script>""")
        return httpx.Response(200, text=f"""
          <h1 class="article-title">苏州低空警务</h1>
          <span class="date">发布日期：<b>2026-11-16 10:12</b></span>
          <div class="article-content"><p>{body}</p></div><footer>无关页脚</footer>""")

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        adapter = build_adapter(SPEC, client, max_items=2)
        adapter.reader.sleeper = lambda _: None
        [(first, next_offset), (second, last)] = list(adapter.iter_entry_pages("default"))
        detail = adapter.fetch_detail(first[0])
    assert calls == ["/robots.txt", "/gaj/jwdt/nav_list.shtml", "/gaj/jwdt/nav_list_2.shtml",
                     f"/gaj/jwdt/202611/{1:032x}.shtml"]
    assert next_offset == 1 and last is None and len(first) == len(second) == 1
    assert second[0].published_date == date(2026, 11, 15)
    assert detail.published_at.hour == 10 and detail.published_at.utcoffset() == timedelta(hours=8)
    assert detail.body == body and detail.title == "苏州低空警务"
    assert adapter.diagnostics["robots_unavailable"] == 1


@pytest.mark.parametrize(("status", "headers", "text", "error"), [
    (200, {}, "User-agent: *\nDisallow: /gaj/jwdt/", "robots_disallowed_or_delayed"),
    (302, {"Location": "/rules.txt"}, "", "http_302"),
    (403, {}, "", "http_403"),
    (429, {}, "", "http_429"),
    (503, {}, "", "http_503"),
])
def test_suzhou_stops_for_denials_unrecognized_redirects_and_network_errors(status, headers, text, error):
    def response(request):
        assert request.url.path == "/robots.txt"
        return httpx.Response(status, headers=headers, text=text)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        adapter = build_adapter(SPEC, client, max_items=2)
        with pytest.raises(SourceFetchError, match=error):
            adapter.list_candidates()
