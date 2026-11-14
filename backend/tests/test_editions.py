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


def test_window_is_beijing_eight_and_missing_coverage_is_visible(db):
    from bluepulse_backend.daily_reports import compose_daily, daily_window, load_daily

    assert daily_window("2026-11-08") == (
        datetime(2026, 11, 7, tzinfo=UTC), datetime(2026, 11, 8, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="daily_not_due"):
        compose_daily(db, "2026-11-08", now=daily_window("2026-11-08")[1] - timedelta(seconds=1))
    assert compose_daily(db, "2026-11-08", now=NOW)["pending"]
    assert load_daily(db, "2026-11-08", NOW)["lead"]["title"] == "本期资讯待补"


def test_other_news_has_its_own_daily_section(db, report):
    from bluepulse_backend.daily_reports import compose_daily, load_daily

    item, *_ = report(datetime(2026, 11, 7, 20, tzinfo=UTC), score=95)
    item.topics = ["other"]
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW)
    detail = load_daily(db, "2026-11-08", now=NOW)
    section = next(row for row in detail["sections"] if row["label"] == "其它警务科技")
    assert [row["itemId"] for row in section["items"]] == [item.id]


def test_late_release_updates_same_issue_and_replaces_withdrawn_lead(db, report):
    from bluepulse_backend.daily_reports import compose_daily, load_daily
    from bluepulse_backend.edition_models import DailyIssueRevision

    cutoff = datetime(2026, 11, 8, tzinfo=UTC)
    first, *_ = report(cutoff - timedelta(hours=2), score=95)
    second, *_ = report(cutoff - timedelta(hours=1), score=80)
    late, *_ = report(cutoff - timedelta(minutes=1), released=cutoff + timedelta(minutes=3), score=90)
    compose_daily(db, "2026-11-08", now=cutoff)
    assert load_daily(db, "2026-11-08", cutoff)["highlights"][0]["itemId"] == second.id
    compose_daily(db, "2026-11-08", now=NOW, refresh=True)
    compose_daily(db, "2026-11-09", now=NOW + timedelta(days=1))
    before = load_daily(db, "2026-11-08", now=NOW)
    assert before["leadItemId"] == first.id
    assert [i["itemId"] for i in before["highlights"]] == [late.id, second.id]
    assert load_daily(db, "2026-11-09", now=NOW + timedelta(days=1))["leadItemId"] is None

    first.withdrawn = True
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW)
    after = load_daily(db, "2026-11-08", now=NOW)
    assert after["leadItemId"] == late.id
    assert after["lead"]["leadParagraph"].startswith(late.zh_summary)
    hidden = next(i for s in after["sections"] for i in s["items"] if i["itemId"] == first.id)
    assert hidden["summary"] is None
    assert hidden["sourceUrl"] == ""
    assert hidden["available"] is False
    compose_daily(db, "2026-11-08", now=NOW, reason="纠正引文", actor="maintainer")
    revision = db.scalar(select(DailyIssueRevision).order_by(DailyIssueRevision.version.desc()))
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


def test_daily_respects_embargo_then_updates_original_issue(db, report):
    from bluepulse_backend.daily_reports import compose_daily, load_daily

    cutoff = datetime(2026, 11, 8, tzinfo=UTC)
    delayed, *_ = report(cutoff - timedelta(hours=1))
    delayed.visible_after = cutoff + timedelta(minutes=1)
    db.commit()
    assert compose_daily(db, "2026-11-08", now=cutoff)["pending"]
    assert load_daily(db, "2026-11-08", cutoff)["leadItemId"] is None
    assert compose_daily(db, "2026-11-08", now=NOW, refresh=True)["written"]
    compose_daily(db, "2026-11-09", now=NOW + timedelta(days=1))
    assert load_daily(db, "2026-11-08", NOW)["leadItemId"] == delayed.id
    assert load_daily(db, "2026-11-09", NOW + timedelta(days=1))["leadItemId"] is None


def test_catchup_skips_an_unjudged_window_and_preserves_a_genuine_quiet_issue(db, report):
    from bluepulse_backend.daily_reports import compose_daily, compose_due_reports, load_daily

    first_cutoff = datetime(2026, 11, 5, tzinfo=UTC)
    report(first_cutoff - timedelta(hours=1))
    compose_daily(db, "2026-11-05", now=NOW)
    report(first_cutoff + timedelta(days=1, hours=2), selected=False)
    newer, *_ = report(first_cutoff + timedelta(days=2, hours=1))
    result = compose_due_reports(db, NOW)
    assert result["generated"] == ["2026-11-06", "2026-11-07", "2026-11-08"]
    assert result["failed"] == []
    assert "2026-11-06" in result["pending"]
    assert load_daily(db, "2026-11-07", NOW)["leadItemId"] is not None
    assert load_daily(db, "2026-11-08", NOW)["leadItemId"] == newer.id


def test_worker_records_unjudged_edition_then_rechecks_on_next_tick(db, report):
    from bluepulse_backend.daily_reports import load_daily
    from bluepulse_backend.editorial_models import WorkItem
    from bluepulse_backend.worker import Worker

    now = NOW.replace(hour=23, minute=45)
    worker = Worker(db.get_bind(), httpx.Client, editions_enabled=True, clock=lambda: now)
    worker.tick()
    assert worker.run_one(kinds={"daily"})
    job = db.scalar(select(WorkItem).where(WorkItem.kind == "daily"))
    assert (job.status, job.error, job.result["pending"]) == ("done", None, ["2026-11-08"])
    assert load_daily(db, "2026-11-08", now)["lead"]["title"] == "本期资讯待补"

    report(datetime(2026, 11, 7, 23, tzinfo=UTC), selected=False)
    now += timedelta(minutes=30)
    worker.tick()
    assert worker.run_one(kinds={"daily"})
    assert now.date().isoformat() == "2026-11-09"
    db.expire_all()
    assert load_daily(db, "2026-11-08", now)["leadItemId"] is not None


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
    assert load_daily(db, "2026-11-08", NOW)["leadItemId"] == official.id

    second.participant_key = "another-organization"
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW, reason="确认独立参与方", actor="maintainer")
    issue = load_daily(db, "2026-11-08", NOW)
    assert issue["leadItemId"] == official.id
    assert issue["sections"][0]["items"][0]["otherSources"] == 2
    assert official.selected_at is None


@pytest.mark.parametrize("date_only", [False, True])
def test_recovered_article_moves_to_missing_source_window_once(db, report, date_only):
    from bluepulse_backend.daily_reports import compose_daily, load_daily
    from bluepulse_backend.models import SourceRun

    cutoff = datetime(2026, 11, 8, tzinfo=UTC)
    published = cutoff - timedelta(hours=3)
    late, source, *_ = report(published, selected=False)
    late.first_seen_at = cutoff + timedelta(hours=1)
    late.published_public_at = late.first_seen_at
    if date_only:
        late.published_at = None
        late.published_date = published.date()
    old, *_ = report(published - timedelta(days=20))
    old.first_seen_at = published
    old.backfill_reason = "first-import"
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW)
    compose_daily(db, "2026-11-09", now=NOW + timedelta(days=1))
    assert load_daily(db, "2026-11-08", NOW)["leadItemId"] == late.id
    assert old.id not in str(load_daily(db, "2026-11-08", NOW))
    assert load_daily(db, "2026-11-09", NOW + timedelta(days=1))["leadItemId"] is None
    db.add(SourceRun(source_id=source.id, started_at=cutoff - timedelta(hours=1),
                     finished_at=cutoff - timedelta(minutes=50), status="no_candidates"))
    db.commit()
    compose_daily(db, "2026-11-08", now=NOW + timedelta(days=1), refresh=True)
    compose_daily(db, "2026-11-09", now=NOW + timedelta(days=1), refresh=True)
    assert load_daily(db, "2026-11-08", NOW + timedelta(days=1))["leadItemId"] is None
    assert load_daily(db, "2026-11-09", NOW + timedelta(days=1))["leadItemId"] == late.id


def test_daily_scheduler_enqueues_boundary_separately_from_other_editions(db):
    from bluepulse_backend.editorial_models import WorkItem
    from bluepulse_backend.worker import WORKER_LANES, Worker

    cutoff = datetime(2026, 11, 8, tzinfo=UTC)
    now = cutoff - timedelta(seconds=1)
    worker = Worker(db.get_bind(), httpx.Client, editions_enabled=True,
                    clock=lambda: now)
    worker.schedule_daily()
    assert worker.run_one(kinds={"daily"})
    now = cutoff + timedelta(seconds=2)
    worker.schedule_daily()
    worker.schedule_daily()
    assert worker.run_one(kinds={"daily"})
    jobs = db.scalars(select(WorkItem).order_by(WorkItem.due_at)).all()
    assert [job.kind for job in jobs] == ["daily", "daily"]
    assert jobs[-1].result["startedAt"] == now.isoformat()
    assert jobs[-1].result["generated"] == ["2026-11-08"]
    assert ({"daily"}, 1) in WORKER_LANES


def test_due_reports_keep_later_issues_running_and_quiet_requires_coverage(db, report, monkeypatch):
    from bluepulse_backend import daily_reports as daily
    from bluepulse_backend.edition_models import DailyIssueRevision
    from bluepulse_backend.models import Source, SourceRun

    source = Source(slug="covered", name="Covered", excerpt_allowed=True)
    db.add(source)
    db.flush()
    start, cutoff = daily.daily_window("2026-11-08")
    for end in (start, cutoff):
        db.add(SourceRun(source_id=source.id, started_at=end - timedelta(hours=1),
                         finished_at=end - timedelta(minutes=5), status="no_candidates"))
    db.commit()
    original = daily.compose_daily

    def fail_one(session, key, **kwargs):
        if key == "2026-11-07":
            raise RuntimeError("synthetic single-issue failure")
        return original(session, key, **kwargs)

    monkeypatch.setattr(daily, "compose_daily", fail_one)
    result = daily.compose_due_reports(db, cutoff)
    assert result["generated"] == ["2026-11-08"]
    assert result["failed"] == ["2026-11-07"]
    assert daily.load_daily(db, "2026-11-08", cutoff)["lead"]["title"] == "警务科技动态平静"

    item, *_ = report(cutoff - timedelta(minutes=1), source=source, selected=False)
    assert daily.compose_due_reports(db, NOW)["updated"] == ["2026-11-08"]
    assert daily.load_daily(db, "2026-11-08", NOW)["leadItemId"] == item.id
    assert daily.compose_due_reports(db, NOW)["updated"] == []
    assert [row.version for row in db.scalars(select(DailyIssueRevision))] == [1]


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
