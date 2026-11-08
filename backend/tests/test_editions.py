import asyncio
from datetime import UTC, datetime, timedelta
from itertools import count

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bluepulse_backend.db import Base


NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


@pytest.fixture
def db():
    from bluepulse_backend import edition_models, editorial_models

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def report(db):
    from bluepulse_backend.editorial_models import Story, StorySignal
    from bluepulse_backend.models import FactGroup, FactReport, Material, Source

    ids = count(1)

    def add(at, *, released=None, source=None, story=None, fact=None, score=80, selected=True, title=None):
        number = next(ids)
        title = title or f"警务设备进展 {number}"
        url = f"https://agency.test/news/{number}"
        if source is None:
            source = Source(slug=f"source-{number}", name=f"Source {number}",
                            excerpt_allowed=True, tier="T1")
            db.add(source)
        if story is None:
            story = Story(title=title, created_at=at)
            db.add(story)
        db.flush()
        if fact is None:
            fact = FactGroup(identity_key=f"fact-{number}", title=title, story_id=story.id, anchor_at=at)
            db.add(fact)
        article = Material(
            canonical_url=url, source_url=url, source_id=source.id, source_title=title,
            source_body="A supported original report. " * 40,
            zh_title=title, zh_summary=f"{title}的公开报道。", content_hash=str(number),
            language="en", public=True, relevant=True, body_status="full_text",
            published_at=at, published_sort_at=at, first_seen_at=at, timeline_kind="fresh",
            published_public_at=released or at, selected_at=(released or at) if selected else None,
            importance_score=score, featured_candidate=selected,
            editorial_revision=1, editorial_scope="single", grouping_value=True,
            grouping_status="complete", selection_status="qualified" if selected else "below_threshold",
            topics=["practice"],
        )
        db.add(article)
        db.flush()
        db.add(FactReport(material_id=article.id, fact_id=fact.id, revision=1))
        db.add(StorySignal(story_id=story.id, material_id=article.id, revision=1,
                           observed_at=at, participant_key=source.id, kind="editorial"))
        db.commit()
        return article, source, story, fact

    return add


def test_window_is_beijing_eight_and_unjudged_cannot_publish(db):
    from bluepulse_backend.daily_reports import DailyUnjudged, compose_daily, daily_window

    assert daily_window("2026-11-08") == (
        datetime(2026, 11, 7, tzinfo=UTC), datetime(2026, 11, 8, tzinfo=UTC),
    )
    with pytest.raises(DailyUnjudged):
        compose_daily(db, "2026-11-08", now=NOW)


def test_frozen_issue_assigns_post_cutoff_release_to_next_day_and_replaces_withdrawn_lead(db, report):
    from bluepulse_backend.daily_reports import compose_daily, load_daily
    from bluepulse_backend.edition_models import DailyIssueRevision

    cutoff = datetime(2026, 11, 8, tzinfo=UTC)
    first, *_ = report(cutoff - timedelta(hours=2), score=95)
    second, *_ = report(cutoff - timedelta(hours=1), score=80)
    late, *_ = report(cutoff - timedelta(minutes=5), released=cutoff, score=90)
    compose_daily(db, "2026-11-08", now=NOW)
    compose_daily(db, "2026-11-09", now=NOW + timedelta(days=1))
    before = load_daily(db, "2026-11-08", now=NOW)
    assert before["leadItemId"] == first.id
    assert [i["itemId"] for i in before["highlights"]] == [second.id]
    assert load_daily(db, "2026-11-09", now=NOW + timedelta(days=1))["leadItemId"] == late.id

    first.withdrawn = True
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW)
    after = load_daily(db, "2026-11-08", now=NOW)
    assert after["leadItemId"] == second.id
    assert after["lead"]["leadParagraph"] == second.zh_summary
    hidden = next(i for s in after["sections"] for i in s["items"] if i["itemId"] == first.id)
    assert hidden["summary"] is None
    assert hidden["sourceUrl"] == ""
    assert hidden["available"] is False
    compose_daily(db, "2026-11-08", now=NOW, reason="纠正引文", actor="maintainer")
    revision = db.scalar(select(DailyIssueRevision))
    assert revision.reason == "纠正引文"
    assert revision.actor == "maintainer"
    assert revision.content["main"][0]["itemId"] == first.id


def test_daily_keeps_one_event_and_two_main_entries_per_source(db, report):
    from bluepulse_backend.daily_reports import compose_daily, load_daily

    start = datetime(2026, 11, 7, tzinfo=UTC)
    lead, source, story, fact = report(start + timedelta(hours=1), score=95)
    report(start + timedelta(hours=2), source=source, story=story, fact=fact)
    development, *_ = report(start + timedelta(hours=3), source=source, story=story)
    other, *_ = report(start + timedelta(hours=4), source=source, score=85)
    flash, *_ = report(start + timedelta(hours=5), source=source, score=70)
    compose_daily(db, "2026-11-08", now=NOW)
    issue = load_daily(db, "2026-11-08", now=NOW)
    assert issue["leadItemId"] == lead.id
    assert issue["metrics"]["totalEvents"] == 2
    assert {i["itemId"] for i in issue["sections"][0]["items"]} == {lead.id, other.id}
    assert issue["sections"][0]["items"][0]["related"][0]["itemId"] == development.id
    assert [i["itemId"] for i in issue["flashes"]] == [flash.id]


def test_daily_later_visibility_release_governs_assignment_even_when_already_selected(db, report):
    from bluepulse_backend.daily_reports import DailyUnjudged, compose_daily, load_daily

    cutoff = datetime(2026, 11, 8, tzinfo=UTC)
    delayed, *_ = report(cutoff - timedelta(hours=1))
    delayed.visible_after = cutoff
    db.commit()
    with pytest.raises(DailyUnjudged):
        compose_daily(db, "2026-11-08", now=NOW)
    compose_daily(db, "2026-11-09", now=NOW + timedelta(days=1))
    assert load_daily(db, "2026-11-09", NOW + timedelta(days=1))["leadItemId"] == delayed.id


def test_catchup_skips_an_unjudged_window_and_preserves_a_genuine_quiet_issue(db, report):
    from bluepulse_backend.daily_reports import compose_daily, compose_due_reports, load_daily

    first_cutoff = datetime(2026, 11, 5, tzinfo=UTC)
    report(first_cutoff - timedelta(hours=1))
    compose_daily(db, "2026-11-05", now=NOW)
    report(first_cutoff + timedelta(days=1, hours=2), selected=False)
    newer, *_ = report(first_cutoff + timedelta(days=2, hours=1))
    result = compose_due_reports(db, NOW)
    assert result == {"generated": ["2026-11-07", "2026-11-08"], "failed": ["2026-11-06"]}
    quiet = load_daily(db, "2026-11-07", NOW)
    assert quiet["leadItemId"] is None
    assert quiet["lead"]["title"] == "警务科技动态平静"
    assert quiet["prev"] == "2026-11-05"
    assert quiet["next"] == "2026-11-08"
    assert load_daily(db, "2026-11-08", NOW)["leadItemId"] == newer.id


def test_daily_remembers_related_facts_and_still_carries_day_of_only_followups(db, report):
    from bluepulse_backend.daily_reports import compose_daily, load_daily

    cutoff = datetime(2026, 11, 8, tzinfo=UTC)
    _, source, story, _ = report(cutoff - timedelta(hours=4), score=98)
    _, _, _, related_fact = report(cutoff - timedelta(hours=3), story=story)
    source.tier = "T2"
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW)
    repeated, *_ = report(cutoff + timedelta(hours=1), source=source, story=story, fact=related_fact, score=99)
    development, *_ = report(cutoff + timedelta(hours=2), source=source, story=story, score=60)
    compose_daily(db, "2026-11-09", now=NOW + timedelta(days=1))
    issue = load_daily(db, "2026-11-09", NOW + timedelta(days=1))
    assert issue["leadItemId"] == development.id
    assert issue["sections"][0]["items"][0]["followUp"] == "2026-11-08"
    assert repeated.id not in str(issue)


def test_daily_fills_in_official_fact_only_after_three_independent_participants(db, report):
    from bluepulse_backend.daily_reports import compose_daily, load_daily

    start = datetime(2026, 11, 7, tzinfo=UTC)
    official, first, story, fact = report(start + timedelta(hours=1), selected=False)
    _, second, *_ = report(start + timedelta(hours=2), story=story, fact=fact, selected=False)
    _, third, *_ = report(start + timedelta(hours=3), story=story, fact=fact, selected=False)
    second.tier = third.tier = "T2"
    first.owner_entity = "Joint Lab"
    second.owner_entity = " JOINT LAB "
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW)
    assert load_daily(db, "2026-11-08", NOW)["leadItemId"] is None

    second.participant_key = "another-organization"
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW, reason="确认独立参与方", actor="maintainer")
    issue = load_daily(db, "2026-11-08", NOW)
    assert issue["leadItemId"] == official.id
    assert issue["sections"][0]["items"][0]["otherSources"] == 2
    assert official.selected_at is None


def test_hot_strip_keeps_saved_rank_gaps_and_requires_three_visible_stories(db, report):
    from bluepulse_backend.hotspots import compute_hot_ranking, load_hot, load_hot_strip

    representatives = []
    for hour in (4, 3, 2, 1):
        first, _, story, fact = report(NOW - timedelta(hours=hour), score=99)
        report(NOW - timedelta(hours=hour), story=story, fact=fact, score=80)
        representatives.append(first)
    compute_hot_ranking(db, NOW)
    assert [entry["rank"] for entry in load_hot_strip(db, NOW)] == [1, 2, 3, 4]
    representatives[-1].withdrawn = True
    db.commit()
    assert [entry["rank"] for entry in load_hot_strip(db, NOW)] == [2, 3, 4]
    representatives[-2].withdrawn = True
    db.commit()
    assert [entry["rank"] for entry in load_hot(db, NOW)["entries"]] == [3, 4]
    assert load_hot_strip(db, NOW) is None


def test_hot_rank_normalizes_independent_participants_and_hides_withdrawn_representative(db, report):
    from bluepulse_backend.hotspots import compute_hot_ranking, load_hot, snapshot_heat
    from bluepulse_backend.models import SourceRun

    lead, first, story, fact = report(NOW - timedelta(hours=24), score=99)
    _, second, *_ = report(NOW - timedelta(hours=1), story=story, fact=fact)
    first.participant_key = "joint-police-office"
    second.participant_key = "joint-police-office"
    _, third, *_ = report(NOW - timedelta(hours=2), story=story, fact=fact)
    for source in (first, second, third):
        db.add(SourceRun(source_id=source.id, started_at=NOW - timedelta(days=10),
                         finished_at=NOW, status="completed"))
    db.commit()
    snapshot_heat(db, NOW)
    compute_hot_ranking(db, NOW)
    entry, = load_hot(db, NOW)["entries"]
    assert entry["participantCount"] == 2
    assert entry["heat"] == 19.2
    assert len(entry["spark"]) == 25
    assert entry["spark"][:-1] == [None] * 24
    assert entry["spark"][-1] == 19.2
    assert entry["trend"] == "up"
    lead.withdrawn = True
    db.commit()
    assert load_hot(db, NOW)["entries"] == []


def test_incomplete_hour_is_null_until_a_successful_collection_repairs_it(db, report):
    from bluepulse_backend.hotspots import compute_hot_ranking, load_hot, snapshot_heat
    from bluepulse_backend.models import SourceRun

    _, first, story, fact = report(NOW - timedelta(hours=7), score=99)
    _, second, *_ = report(NOW - timedelta(hours=4), story=story, fact=fact)
    for source in (first, second):
        db.add(SourceRun(source_id=source.id, started_at=NOW - timedelta(days=10),
                         finished_at=NOW - timedelta(hours=4), status="completed"))
    db.commit()
    snapshot_heat(db, NOW)
    compute_hot_ranking(db, NOW)
    entry, = load_hot(db, NOW)["entries"]
    assert entry["trend"] == "unknown"
    assert entry["spark"][-1] is None

    later = NOW + timedelta(hours=1)
    for source in (first, second):
        db.add(SourceRun(source_id=source.id, started_at=NOW, finished_at=later, status="no_candidates"))
    db.commit()
    assert snapshot_heat(db, later)["repaired"] == 1
    assert load_hot(db, later)["entries"][0]["spark"][-1] == 17.1


def test_edition_http_returns_real_empty_state_then_published_issue(db, report, monkeypatch):
    from bluepulse_backend import daily_reports, edition_routes, hotspots

    for module in (daily_reports, edition_routes, hotspots):
        monkeypatch.setattr(module, "now_utc", lambda: NOW)

    def get_session():
        with Session(db.get_bind()) as session:
            yield session

    app = FastAPI()
    router = APIRouter(prefix="/api/v1")
    edition_routes.register_editions(router, get_session, lambda status, code, message: HTTPException(status, code))
    app.include_router(router)

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://pulse.test/api/v1/") as client:
            assert (await client.get("site/hot")).json() == {"computedAt": None, "windowHours": 48, "entries": []}
            daily_path = "site/reports/daily"
            assert (await client.get(f"{daily_path}/latest-page")).json() == {"index": [], "report": None}
            assert (await client.get(f"{daily_path}/2026-11-08")).status_code == 404
            assert (await client.get(f"{daily_path}/2026-02-30")).status_code == 404
            article, *_ = report(datetime(2026, 11, 7, 23, tzinfo=UTC))
            daily_reports.compose_daily(db, "2026-11-08", now=NOW)

            latest = (await client.get(f"{daily_path}/latest-page")).json()
            assert latest["report"]["leadItemId"] == article.id
            assert latest["report"]["issueNumber"] == 1
            assert (await client.get(f"{daily_path}/navigation/2026-11-08")).json() == {"items": latest["index"]}
            assert (await client.get(f"{daily_path}/months/2026-11")).json() == {"items": latest["index"]}
            assert (await client.get(daily_path)).json()["items"][0]["count"] == 1
            assert (await client.get(f"{daily_path}/2026-11-08")).json() == latest["report"]

    asyncio.run(check())
