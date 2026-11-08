from __future__ import annotations

import httpx
import pytest

from bluepulse_backend.europol_source import FEED as EUROPOL_FEED, EuropolNewsAdapter
from bluepulse_backend.live_sources import BoundedHTTP, SourceFetchError
from bluepulse_backend.spf_source import LISTING as SPF_LISTING, SpfPoliceLifeAdapter
from bluepulse_backend.statescoop_source import FEED as STATESCOOP_FEED, StateScoopAdapter
from bluepulse_backend.top5_probe import JIANGSU_LIST, NPCC_LIST, HtmlEvidenceProbe


@pytest.mark.parametrize("adapter, options, listing, suffix, rss", [
    (StateScoopAdapter, {}, STATESCOOP_FEED, "/digital-evidence-{n}/", True),
    (EuropolNewsAdapter, {}, EUROPOL_FEED, "/media-press/newsroom/news/digital-evidence-{n}", True),
    (SpfPoliceLifeAdapter, {}, SPF_LISTING, "/Media-Hub/Police-Life/2026/11/Digital-Evidence-{n}", False),
    (HtmlEvidenceProbe, {"kind": "npcc"}, NPCC_LIST, "/releases/digital-evidence-{n}", False),
    (HtmlEvidenceProbe, {"kind": "jiangsu"}, JIANGSU_LIST, "/art/2026/11/7/art_6372_{n}.html", False),
])
def test_listing_reads_all_items_without_detail_and_fresh_detail_reader_checks_robots(
        adapter, options, listing, suffix, rss):
    host = httpx.URL(listing).host
    paths = [suffix.format(n=index) for index in range(1, 5)]
    urls = [f"https://{host}{path}" for path in paths]
    if rss:
        entries = "".join(f"<item><title>Digital evidence {i}</title><link>{url}</link></item>"
                          for i, url in enumerate(urls))
        body = f"<rss><channel>{entries}</channel></rss>"
    else:
        body = "".join(f"<a href='{url}'>Digital evidence {i}</a>" for i, url in enumerate(urls))
        if options.get("kind") == "jiangsu":
            body = f"<record><![CDATA[{body}]]></record>"
    calls = []
    blocked_path = paths[-1]

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=f"User-agent: *\nDisallow: {blocked_path}\n")
        assert str(request.url) == listing
        return httpx.Response(200, text=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        http = BoundedHTTP(client, allowed_hosts={host}, delay_seconds=0)
        source = adapter(http, max_items=2, sleeper=lambda _: None, **options)
        candidates = source.list_candidates()
        assert [item.url for item in candidates] == urls
        assert all(item.body is None for item in candidates)
        assert calls == [f"https://{host}/robots.txt", listing]
        fresh = adapter(http, max_items=2, sleeper=lambda _: None, **options)
        with pytest.raises(SourceFetchError, match="robots_disallowed"):
            fresh.fetch_detail(candidates[-1])
        assert calls[-1] == f"https://{host}/robots.txt"
