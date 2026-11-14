from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend import worker as worker_module
from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.editorial_models import WorkItem
from bluepulse_backend.models import Material, Source, SourceRun
from bluepulse_backend.pipeline import Candidate


NOW = datetime(2026, 11, 8, 5, tzinfo=UTC)


def candidate(key, *, published=NOW, body=None):
    return Candidate(f"https://example.test/{key}", f"Police technology report {key}",
                     body=body, published_at=published, language="en")


def test_later_entries_survive_duplicate_heads_and_detail_is_independent(tmp_path):
    from bluepulse_backend.collection_flow import admit_page, apply_detail

    engine = make_engine(f"sqlite:///{tmp_path / 'collector.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(slug="fixture", name="Fixture", allowed_hosts=["example.test"])
        session.add(source)
        session.flush()
        first = SourceRun(source_id=source.id)
        session.add(first)
        session.flush()
        rows = [candidate("a", body="Verified body." * 50), candidate("b", body="Different evidence." * 50)]
        admit_page(session, source, first, rows, NOW, {})
        original = session.scalar(select(Material).where(Material.canonical_url.endswith("/a")))
        source.collection_initialized_at = NOW
        second = SourceRun(source_id=source.id)
        session.add(second)
        session.flush()
        admit_page(session, source, second,
                   [candidate("a"), candidate("b"), candidate("c"), candidate("d"),
                    candidate("historic", published=NOW - timedelta(days=3))],
                   NOW + timedelta(minutes=15), {})
        assert original.revision == 1 and original.source_body == rows[0].body
        assert {row.canonical_url.rsplit("/", 1)[-1] for row in session.scalars(select(Material))} == {"a", "b", "c", "d"}
        item = session.scalar(select(Material).where(Material.canonical_url.endswith("/c")))
        assert item.collection_state == "pending" and not item.source_body
        job = next(job for job in session.scalars(select(WorkItem)) if job.payload["url"].endswith("/c"))
        filled = apply_detail(session, source, job.payload, candidate("c", body="Original source." * 50), NOW)
        assert filled.id == item.id and filled.revision == 2 and filled.collection_state == "complete"


def test_first_import_limits_after_deduplication_and_retains_cursor_progress(tmp_path):
    from bluepulse_backend.collection_flow import admit_page

    engine = make_engine(f"sqlite:///{tmp_path / 'initial.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(slug="fixture", name="Fixture", allowed_hosts=["example.test"])
        session.add(source)
        session.flush()
        run = SourceRun(source_id=source.id)
        session.add(run)
        session.flush()
        cursor = {}
        admit_page(session, source, run, [candidate("old", published=NOW - timedelta(days=361))] +
                   [candidate(str(n)) for n in range(20)], NOW, cursor)
        admit_page(session, source, run, [candidate("0")] + [candidate(str(n)) for n in range(20, 40)],
                   NOW, cursor)
        assert len(session.scalars(select(Material)).all()) == 30
        assert len(session.scalars(select(WorkItem)).all()) == 30


def test_detail_retries_twice_then_releases_real_excerpt_for_analysis(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from bluepulse_backend.collection_flow import admit_page
    from bluepulse_backend.live_sources import SourceFetchError
    from bluepulse_backend.receipts import Budget

    class Adapter:
        def fetch_detail(self, candidate):
            raise SourceFetchError("http_503")

    monkeypatch.setattr(worker_module, "build_adapter", lambda *_args, **_kw: Adapter())
    engine = make_engine(f"sqlite:///{tmp_path / 'detail.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(slug="govuk", name="Fixture", allowed_hosts=["www.gov.uk"])
        session.add(source)
        session.flush()
        run = SourceRun(source_id=source.id)
        session.add(run)
        session.flush()
        admit_page(session, source, run, [
            Candidate("https://www.gov.uk/government/news/fixture", "Source headline",
                      summary="Actual source excerpt", published_at=NOW, language="en")
        ], NOW, {})
        session.commit()

    clock = [NOW]
    worker = worker_module.Worker(engine, lambda: nullcontext(SimpleNamespace()), clock=lambda: clock[0],
                                  budget=Budget(10, 10, 10), collect_enabled=True)
    for attempt in (1, 2):
        assert worker.run_one(kinds={"extract"})
        with Session(engine) as session:
            extract = session.scalar(select(WorkItem).where(WorkItem.kind == "extract"))
            assert extract.status == "pending" and extract.attempts == attempt
            assert session.scalar(select(Material)).collection_state == "pending"
            assert session.scalar(select(WorkItem).where(WorkItem.kind == "analyze")) is None
        clock[0] += timedelta(minutes=9)
        assert not worker.run_one(kinds={"extract"})
        clock[0] += timedelta(minutes=1)
    assert worker.run_one(kinds={"extract"})
    with Session(engine) as session:
        item = session.scalar(select(Material))
        assert item.collection_state == "unconfirmed" and item.source_summary == "Actual source excerpt"
        assert session.scalar(select(WorkItem).where(WorkItem.kind == "analyze")).status == "pending"


def test_worker_recovery_checks_enabled_sources_despite_old_backoff(tmp_path):
    from bluepulse_backend.source_collection import SOURCES, ensure_source

    engine = make_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for spec in SOURCES.values():
            source = ensure_source(session, spec)
            source.next_fetch_at = NOW + timedelta(hours=2)
            source.enabled = source.slug != "ccgp-policing-tech"
        session.commit()

    worker = worker_module.Worker(engine, None, clock=lambda: NOW, collect_enabled=True)
    worker.tick()
    with Session(engine) as session:
        assert session.scalars(select(WorkItem).where(WorkItem.kind == "collect")).first() is None
    worker.tick(recover_collection=True)
    worker.tick(recover_collection=True)
    with Session(engine) as session:
        jobs = session.scalars(select(WorkItem).where(WorkItem.kind == "collect")).all()
        assert len(jobs) == len(SOURCES) - 1
        assert {job.payload["slug"] for job in jobs} == set(SOURCES) - {"ccgp-policing-tech"}


def test_partial_listing_is_replayed_from_head_to_recover_shifted_entries(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from bluepulse_backend.live_sources import SourceFetchError
    from bluepulse_backend.source_collection import SOURCES, ensure_source

    starts = []
    clock = [NOW]

    class Adapter:
        def iter_listing_pages(self, *, start=0):
            starts.append(start)
            def item(key):
                return Candidate(f"https://www.gov.uk/government/news/{key}", key,
                                 published_at=NOW - timedelta(days=5), body=key * 350)
            if len(starts) == 1:
                yield [item("known")], 1
                raise SourceFetchError("timeout")
            if start == 0:
                yield [item("new-head")], 1
            yield [item("known"), item("archive")], None

    monkeypatch.setattr(worker_module, "build_adapter", lambda *_args, **_kw: Adapter())
    engine = make_engine(f"sqlite:///{tmp_path / 'interrupted.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = ensure_source(session, SOURCES["govuk"])
        source.collection_initialized_at = NOW - timedelta(days=30)
        session.commit()

    worker = worker_module.Worker(engine, lambda: nullcontext(SimpleNamespace()), clock=lambda: clock[0],
                                  slugs=["govuk"], collect_enabled=True)
    worker.tick()
    assert worker.run_one(kinds={"collect"})
    with Session(engine) as session:
        assert session.scalar(select(SourceRun)).status == "failed"
    clock[0] += timedelta(hours=1)
    worker.tick(recover_collection=True)
    assert worker.run_one(kinds={"collect"})
    with Session(engine) as session:
        assert starts == [0, 0]
        assert {(row.source_title, row.revision) for row in session.scalars(select(Material))} == {
            ("new-head", 1), ("known", 1), ("archive", 1),
        }
        assert set(session.scalars(select(SourceRun.status))) == {"failed", "completed"}


def test_worker_stop_preserves_committed_pages_and_does_not_fetch_more(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from bluepulse_backend.source_collection import SOURCES, ensure_source

    class Adapter:
        def iter_listing_pages(self, *, start=0):
            worker.stopping.set()
            yield [Candidate("https://www.gov.uk/government/news/first", "First", published_at=NOW)], 1
            raise AssertionError("the worker should stop before requesting another page")

    monkeypatch.setattr(worker_module, "build_adapter", lambda *_args, **_kw: Adapter())
    engine = make_engine(f"sqlite:///{tmp_path / 'shutdown.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_source(session, SOURCES["govuk"])
    worker = worker_module.Worker(engine, lambda: nullcontext(SimpleNamespace()), clock=lambda: NOW,
                                  slugs=["govuk"], collect_enabled=True)
    worker.tick()
    assert worker.run_one(kinds={"collect"})
    with Session(engine) as session:
        assert session.scalar(select(Material)).source_title == "First"
        assert session.scalar(select(SourceRun)).error_code == "worker_interrupted"
        assert session.scalar(select(Source)).collection_initialized_at is None


def test_transient_listing_and_detail_failures_are_retried(tmp_path):
    from bluepulse_backend.collection_flow import admit_page, schedule_after_fetch

    engine = make_engine(f"sqlite:///{tmp_path / 'retry.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(slug="fixture", name="Fixture", allowed_hosts=["example.test"],
                        collection_initialized_at=NOW, interval_minutes=60)
        session.add(source)
        session.flush()
        schedule_after_fetch(source, NOW, success=False, error="transport_error")
        assert source.next_fetch_at == NOW + timedelta(minutes=10)

        run = SourceRun(source_id=source.id)
        session.add(run)
        session.flush()
        rows = [candidate("failed"), candidate("denied")]
        admit_page(session, source, run, rows, NOW, {})
        jobs = {job.payload["url"].rsplit("/", 1)[-1]: job for job in session.scalars(select(WorkItem))}
        for name, error in (("failed", "timeout"), ("denied", "robots_disallowed")):
            job = jobs[name]
            job.status, job.attempts, job.result = "done", 3, {"error": error}
            session.get(Material, job.payload["material_id"]).collection_state = "unconfirmed"
        run = SourceRun(source_id=source.id)
        session.add(run)
        session.flush()
        admit_page(session, source, run, rows, NOW + timedelta(hours=1), {})
        assert (jobs["failed"].status, jobs["failed"].attempts) == ("pending", 0)
        assert (jobs["denied"].status, jobs["denied"].attempts) == ("done", 3)
