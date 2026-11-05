from __future__ import annotations

from datetime import date
import hashlib
import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.api import _card
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.live_sources import BoundedHTTP
from bluepulse_backend.models import Material, MaterialRevision
from bluepulse_backend.police_science_source import (
    HOST, PoliceScienceAdapter, news_urls_from_sitemap, parse_news_html,
)
from bluepulse_backend.pipeline import Candidate, _content_hash
from bluepulse_backend.source_collection import SOURCES, build_adapter, collect
from bluepulse_backend.schemas import ArticleCardOut


def test_sitemap_uses_only_same_host_news_article_paths():
    xml = b"""<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://science.police.uk/news-and-events/news/ai-pilot/</loc></url>
      <url><loc>https://science.police.uk/news-and-events/news/ai-pilot/</loc></url>
      <url><loc>https://evil.example/news-and-events/news/unsafe/</loc></url>
      <url><loc>https://science.police.uk/news-and-events/news/</loc></url>
    </urlset>"""
    assert news_urls_from_sitemap(xml) == ["https://science.police.uk/news-and-events/news/ai-pilot/"]


def test_date_field_does_not_revise_existing_sources_without_date_precision():
    candidate = Candidate(url="https://example.test/story", title="Old source", body="Article body")
    old_payload = ["Old source", "Article body", "", None]
    expected = hashlib.sha256(json.dumps(old_payload, ensure_ascii=False).encode()).hexdigest()
    assert _content_hash(candidate) == expected


def test_article_parser_keeps_only_news_body_and_date_precision():
    html = """<h1 class='site-title'>Site name</h1>
      <article class='sparticle article_news'>
        <div class='event_date'>PUBLISHED: 22 September 2026</div>
        <h1 class='article_title'>Police AI pilot</h1>
        <div class='article_copy'><p>Police evaluated an AI system in an operational setting.</p>
          <p>The report describes evidence, safeguards, and deployment limitations.</p></div>
      </article><footer>Unrelated links</footer>"""
    article = parse_news_html(html)
    assert article.title == "Police AI pilot" and article.published_date == "2026-09-22"
    assert "safeguards" in article.body and "Site name" not in article.body
    assert "Unrelated" not in article.body


def test_self_redirect_robots_can_be_collected_but_transport_failure_cannot():
    article_url = f"https://{HOST}/news-and-events/news/ai-pilot/"
    sitemap = f"<urlset><url><loc>{article_url}</loc></url></urlset>"
    body = "Police science teams evaluated an AI workflow and published the findings. " * 4
    article = ("<div class='event_date'>PUBLISHED: 22 September 2026</div>"
               "<h1 class='article_title'>Police AI pilot</h1>"
               f"<div class='article_copy'><p>{body}</p></div>")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(301, headers={"location": "/robots.txt"})
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, text=sitemap)
        return httpx.Response(200, text=article)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = PoliceScienceAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                       max_items=1, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert calls.count("/robots.txt") == 7
    assert adapter.diagnostics["robots_status"] == "self_redirect_unavailable"
    assert len(rows) == 1 and rows[0].published_at is None
    assert rows[0].published_date == date(2026, 9, 22)
    assert body.strip() in rows[0].body

    def broken(request):
        raise httpx.ConnectError("network down")

    with httpx.Client(transport=httpx.MockTransport(broken)) as client:
        adapter = PoliceScienceAdapter(BoundedHTTP(client, allowed_hosts={HOST}, delay_seconds=0),
                                       max_items=1, sleeper=lambda _: None)
        try:
            adapter.candidates()
        except Exception as exc:
            assert getattr(exc, "code", None) == "robots_transport_error"
        else:
            assert False, "transport failure must stop collection"


def test_collection_persists_date_without_invented_time(tmp_path):
    article_url = f"https://{HOST}/news-and-events/news/ai-pilot/"
    body = "Police science teams evaluated an AI workflow and published the findings. " * 4

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /admin/\n")
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, text=f"<urlset><url><loc>{article_url}</loc></url></urlset>")
        return httpx.Response(200, text=(
            "<div class='event_date'>PUBLISHED: 22 September 2026</div>"
            "<h1 class='article_title'>Police AI pilot</h1>"
            f"<div class='article_copy'><p>{body}</p></div>"))

    engine = make_engine(f"sqlite:///{(tmp_path / 'collection.db').as_posix()}")
    Base.metadata.create_all(engine)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, Session(engine) as session:
        adapter = build_adapter(SOURCES["police-science"], client, max_items=1)
        adapter.sleeper = lambda _: None
        adapter.http.delay_seconds = 0
        result = collect(session, SOURCES["police-science"], adapter)
        assert result["status"] == "completed" and result["discoveries"] == {"new": 1}
        material = session.scalar(select(Material))
        revision = session.scalar(select(MaterialRevision))
        assert material.published_at is None and material.published_date == date(2026, 9, 22)
        assert revision.published_date == material.published_date
        assert material.body_status == "full_text" and not material.public
        assert ArticleCardOut.model_validate(_card(material)).published_date == "2026-09-22"
        assert collect(session, SOURCES["police-science"], adapter)["discoveries"] == {"duplicate": 1}
    engine.dispose()
