from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bluepulse_backend.api import create_app
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.material_identity import publication_clock
from bluepulse_backend.models import Discovery, Material, Source
from bluepulse_backend.pipeline import AnalysisResult, Candidate, MockAnalyzer, MockSourceAdapter, ingest, process_pending


def _source(session: Session, slug: str, host: str) -> Source:
    source = Source(slug=slug, name=slug, region="foreign", country_code="GB",
                    language="en", source_type="official", topics=[],
                    allowed_hosts=[host], excerpt_allowed=True)
    session.add(source)
    session.commit()
    return source


def _answer() -> AnalysisResult:
    return AnalysisResult(relevant=True, title_zh="测试", summary_zh="内部测试摘要",
                          topics=("practice",), importance_score=50)


def test_same_copy_is_linked_but_other_reporting_is_preserved(tmp_path):
    address = f"sqlite:///{(tmp_path / 'copies.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    body = " ".join(
        f"Project {index} uses digital evidence to support victims and witnesses across the force."
        for index in range(35))
    day = date.today() - timedelta(days=1)
    with Session(engine) as session:
        npcc = _source(session, "npcc", "news.npcc.test")
        pds = _source(session, "pds", "pds.test")
        title = "National awards shine spotlight on the innovation transforming policing"
        first = Candidate(url="https://news.npcc.test/awards", title=title,
                          body=body + "NPCC attributed note.", published_date=day)
        second = Candidate(url="https://pds.test/awards", title=title,
                           body="Introducing the winners. " + body, published_date=day)
        ingest(session, npcc, MockSourceAdapter([first]))
        ingest(session, pds, MockSourceAdapter([second]))
        rows = session.scalars(select(Material).order_by(Material.source_url)).all()
        assert len(rows) == 2
        primary = next(row for row in rows if row.source_id == npcc.id)
        mirror = next(row for row in rows if row.source_id == pds.id)
        assert mirror.duplicate_of_id == primary.id
        assert mirror.duplicate_reason == "same_title_day_body_overlap"
        assert mirror.source_body and mirror.source_url == second.url
        assert session.scalar(select(func.count()).select_from(Discovery)) == 2
        assert process_pending(session, MockAnalyzer({primary.canonical_url: _answer()})) == {
            "applied": 1, "failed": 0, "unknown": 0}
        assert primary.public and not mirror.public
        assert mirror.state == "duplicate_hidden"
        with TestClient(create_app(address)) as client:
            assert len(client.get("/api/v1/articles?period=all").json()["items"]) == 1
            assert client.get(f"/api/v1/articles/{mirror.id}").status_code == 404
        # A later substantive rewrite must break the link and get a new revision.
        changed = Candidate(url=second.url, title=title,
                            body="A different technology project with no matching facts. " * 18,
                            published_date=day)
        ingest(session, pds, MockSourceAdapter([changed]))
        assert mirror.revision == 2 and mirror.duplicate_of_id is None
        assert process_pending(session, MockAnalyzer({mirror.canonical_url: _answer()}))["applied"] == 1
        with TestClient(create_app(address)) as client:
            assert len(client.get("/api/v1/articles?period=all").json()["items"]) == 2
    engine.dispose()


def test_same_title_different_body_and_exact_url_do_not_conflate(tmp_path):
    address = f"sqlite:///{(tmp_path / 'exact.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        one = _source(session, "nist-one", "nist.test")
        two = _source(session, "nist-two", "nist.test")
        day = date.today()
        first = Candidate(url="https://nist.test/news?id=7&utm_source=feed",
                          title="Public safety technology research results",
                          body="A" * 700, published_date=day)
        other = Candidate(url="https://nist.test/another", title=first.title,
                          body="B" * 700, published_date=day)
        ingest(session, one, MockSourceAdapter([first, other]))
        repeated = Candidate(url="https://nist.test/news?utm_medium=rss&id=7",
                             title=first.title, body=first.body, published_date=day)
        run = ingest(session, two, MockSourceAdapter([repeated]))
        assert session.scalar(select(func.count()).select_from(Material)) == 2
        assert session.scalar(select(Discovery.outcome).where(Discovery.run_id == run.id)) == "duplicate"
        assert all(row.duplicate_of_id is None for row in session.scalars(select(Material)))
    engine.dispose()


def test_primary_revision_releases_mirror_and_reuses_saved_analysis(tmp_path):
    address = f"sqlite:///{(tmp_path / 'relink.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first_source = _source(session, "first", "first.test")
        mirror_source = _source(session, "mirror", "mirror.test")
        title = "National awards shine spotlight on the innovation transforming policing"
        body = " ".join(f"Police project {i} has an independently described capability."
                        for i in range(45))
        day = date.today() - timedelta(days=1)
        first = Candidate(url="https://first.test/awards", title=title, body=body,
                          published_date=day)
        mirror = Candidate(url="https://mirror.test/awards", title=title,
                           body="Publisher introduction. " + body, published_date=day)
        ingest(session, first_source, MockSourceAdapter([first]))
        ingest(session, mirror_source, MockSourceAdapter([mirror]))
        rows = session.scalars(select(Material)).all()
        by_url = {row.source_url: row for row in rows}
        assert by_url[mirror.url].duplicate_of_id == by_url[first.url].id
        assert process_pending(session, MockAnalyzer({by_url[first.url].canonical_url: _answer()}))[
            "applied"] == 1
        changed = Candidate(url=first.url, title=title,
                            body="A separate police procurement update. " * 50,
                            published_date=day)
        ingest(session, first_source, MockSourceAdapter([changed]))
        assert by_url[mirror.url].duplicate_of_id is None
        assert by_url[mirror.url].state == "analysis_pending"
        assert process_pending(session, MockAnalyzer({row.canonical_url: _answer() for row in rows})) == {
            "applied": 2, "failed": 0, "unknown": 0}
        assert by_url[mirror.url].public
    engine.dispose()


def test_date_only_freshness_is_not_an_invented_24_hour_timestamp(tmp_path):
    now = datetime.now(UTC)
    assert publication_clock(None, now.date() - timedelta(days=120), now)[0] == "historical"
    assert publication_clock(None, now.date() + timedelta(days=1), now) == ("unknown", None, None)
    address = f"sqlite:///{(tmp_path / 'dates.db').as_posix()}"
    engine = make_engine(address)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = _source(session, "state", "state.test")
        old = Candidate(url="https://state.test/old", title="Old police technology article",
                        body="old evidence " * 50, published_date=now.date() - timedelta(days=120))
        today = Candidate(url="https://state.test/today", title="Recent police technology article",
                          body="new evidence " * 50, published_date=now.date())
        ingest(session, source, MockSourceAdapter([old, today]))
        rows = {row.source_title: row for row in session.scalars(select(Material))}
        assert rows[old.title].timeline_kind == "historical"
        assert rows[today.title].timeline_kind == "fresh"
        assert rows[today.title].published_at is None and rows[today.title].published_sort_at is not None
        process_pending(session, MockAnalyzer({row.canonical_url: _answer() for row in rows.values()}))
    with TestClient(create_app(address)) as client:
        assert client.get("/api/v1/articles?period=24h").json()["items"] == []
        week = client.get("/api/v1/articles?period=7d").json()["items"]
        assert len(week) == 1 and week[0]["published_date"] == now.date().isoformat()
        all_items = client.get("/api/v1/articles?period=all").json()["items"]
        assert [item["timeline_kind"] for item in all_items] == ["fresh", "historical"]
        first_page = client.get("/api/v1/articles?period=all&limit=1").json()
        assert first_page["items"][0]["published_date"] == now.date().isoformat()
        second_page = client.get("/api/v1/articles", params={
            "period": "all", "limit": 1, "cursor": first_page["next_cursor"]}).json()
        assert second_page["items"][0]["published_date"] == old.published_date.isoformat()
    engine.dispose()
