from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.live_sources import BoundedHTTP, SourceFetchError
from bluepulse_backend.models import Material, Source
from bluepulse_backend.source_collection import SOURCES, build_adapter, collect
from bluepulse_backend.source_expansion import BoundedHtmlSourceAdapter, SITES


CASES = {
    "pds": (
        "<h2 class='post-title entry-title'><a href='https://pds.police.uk/police-tech-update/'>Tech update</a></h2>",
        "<article><h1>Tech update</h1><time datetime='2026-10-27'></time>"
        "<div class='entry-content'><p>Police technology test produced a documented workflow.</p>"
        "<p>Second paragraph with evidence of deployment and evaluation.</p>"
        "<p>Third paragraph describes data handling and technical limits.</p></div>"
        "<div class='related-posts'>Unrelated recommendation</div></article>",
        "https://pds.police.uk/police-tech-update/", datetime(2026, 10, 27, tzinfo=UTC)),
    "biometric": (
        "<h2><a href='https://www.biometricupdate.com/202610/law-enforcement-test'>Police biometrics</a></h2>",
        "<meta property='article:published_time' content='2026-10-25T17:19:43+00:00'>"
        "<meta name='description' content='Police biometric pilot'>"
        "<article><h1>Police biometrics</h1><div class='thecontent'>"
        "<p>Police tested a biometric workflow under public oversight.</p>"
        "<p>Additional paragraph records the method and its limits.</p>"
        "<p>Third paragraph describes safeguards and testing.</p>"
        "<div class='rp4wp-related-posts'>Unrelated recommendation</div></div></article>",
        "https://www.biometricupdate.com/202610/law-enforcement-test",
        datetime(2026, 10, 25, 17, 19, 43, tzinfo=UTC)),
    "nij": (
        "<li class='cta__item'><a href='/topics/articles/technology-test'>Technology test</a></li>",
        "<article><h1>Technology test</h1><div class='field--name-field-date-published'>"
        "<div class='field__label'>Date Published</div><div class='field__item'>October 22, 2024</div></div>"
        "<div class='field--name-body'><p>NIJ evaluated an operational technology.</p>"
        "<p>The report describes its limits and practical application.</p>"
        "<p>Additional methods and measurements are presented.</p></div></article>",
        "https://nij.ojp.gov/topics/articles/technology-test",
        datetime(2024, 10, 22, tzinfo=UTC)),
}


def test_nij_pilot_is_not_in_active_source_catalog():
    assert "nij-equipment-tech" not in SOURCES


@pytest.mark.parametrize("kind", CASES)
def test_bounded_html_source_extracts_listing_detail_date_and_body(kind):
    listing, detail, expected_url, expected_date = CASES[kind]
    config = SITES[kind]
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=listing if str(request.url) == config.listing else detail)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = BoundedHtmlSourceAdapter(
            BoundedHTTP(client, allowed_hosts={config.host}, delay_seconds=0),
            kind=kind, max_items=1, sleeper=lambda _: None)
        rows = adapter.candidates()
    assert requests == [f"https://{config.host}/robots.txt", config.listing, expected_url]
    assert len(rows) == 1 and rows[0].url == expected_url
    if kind in {"pds", "nij"}:
        assert rows[0].published_date == expected_date.date()
        assert rows[0].published_at is None
    else:
        assert rows[0].published_at == expected_date
    assert rows[0].body and len(rows[0].body) >= 120
    assert "Unrelated recommendation" not in rows[0].body
    assert adapter.diagnostics["detail_full_text"] == 1


def test_expansion_source_preserves_media_type_and_duplicate(tmp_path):
    config = SITES["biometric"]
    listing, detail, _, _ = CASES["biometric"]

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=listing if str(request.url) == config.listing else detail)

    engine = make_engine(f"sqlite:///{(tmp_path / 'expansion.db').as_posix()}")
    Base.metadata.create_all(engine)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, Session(engine) as session:
        spec = SOURCES["biometric-update-law-enforcement"]
        adapter = build_adapter(spec, client, max_items=1)
        adapter.sleeper = lambda _: None
        first = collect(session, spec, adapter)
        second = collect(session, spec, adapter)
        source = session.scalar(select(Source))
        material = session.scalar(select(Material))
        assert first["discoveries"] == {"new": 1}
        assert second["discoveries"] == {"duplicate": 1}
        assert source.source_type == "media" and not source.excerpt_allowed
        assert material.body_status == "full_text" and not material.public
    engine.dispose()


def test_expansion_respects_robots_disallow():
    config = SITES["pds"]
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /welcome/blog/\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = BoundedHtmlSourceAdapter(
            BoundedHTTP(client, allowed_hosts={config.host}, delay_seconds=0),
            kind="pds", sleeper=lambda _: None)
        with pytest.raises(SourceFetchError, match="robots_disallowed"):
            adapter.candidates()
    assert requests == [f"https://{config.host}/robots.txt"]
