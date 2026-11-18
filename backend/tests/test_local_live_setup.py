import sqlite3

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bluepulse_backend import cli
from bluepulse_backend.admin_models import AdminAudit, AdminContentOverride
from bluepulse_backend.db import make_engine
from bluepulse_backend.editorial_models import PaidAttempt, WorkItem
from bluepulse_backend.models import Material, Source, now_utc


def test_local_live_bootstrap_reprojects_saved_results_once(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{(tmp_path / 'local.db').as_posix()}")
    cli.initialize()
    engine = make_engine()
    with Session(engine) as session:
        source = session.scalar(select(Source).where(Source.slug == "govuk"))
        assert not source.excerpt_allowed and source.selection_threshold is None
        source.tier = None  # Databases created before source tiers were seeded.

        def saved(suffix, *, withdrawn=False, timeline="fresh"):
            url = f"https://www.gov.uk/{suffix}"
            return Material(source_id=source.id, canonical_url=url, source_url=url, source_title=suffix,
                            zh_summary="Saved model summary", source_body="Original evidence. " * 35,
                            body_status="full_text", content_hash=suffix, language="en", relevant=True, withdrawn=withdrawn,
                            state="publication_hidden", timeline_kind=timeline, grouping_status="complete",
                            revision=1, editorial_revision=1, editorial_data={"scores": [59, 61]})

        ready, blocked, history, withdrawn = saved("ready"), saved("blocked"), saved("old", timeline="historical"), saved("withdrawn", withdrawn=True)
        session.add_all([ready, blocked, history, withdrawn])
        session.flush()
        session.add(AdminContentOverride(material_id=blocked.id, fields={"selected": False}))
        other = session.scalar(select(Source).where(Source.slug == "npcc"))
        session.add(AdminAudit(actor="admin:local", action="source.update", subject=f"source:{other.id}",
                               changes={"before": {"excerpt_allowed": True, "selection_threshold": 60},
                                        "after": {"excerpt_allowed": False, "selection_threshold": None}}))
        session.commit()
        ready_id, blocked_id, history_id, withdrawn_id, source_id = ready.id, blocked.id, history.id, withdrawn.id, source.id

    cli.initialize(local_live=True)
    with Session(engine) as session:
        source = session.get(Source, source_id)
        assert source.excerpt_allowed and source.tier == "T1" and source.selection_threshold == 60
        assert source.full_text_allowed and not source.media_allowed and not source.syndicate_full_text_allowed
        media = session.scalar(select(Source).where(Source.slug == "statescoop-law-enforcement-tech"))
        assert media.excerpt_allowed and media.selection_threshold == 76
        other = session.scalar(select(Source).where(Source.slug == "npcc"))
        assert not other.excerpt_allowed and other.selection_threshold is None
        assert session.get(Material, ready_id).public and session.get(Material, ready_id).featured_candidate
        assert session.get(Material, blocked_id).public and not session.get(Material, blocked_id).featured_candidate
        assert session.get(Material, history_id).public and not session.get(Material, withdrawn_id).public
        jobs = list(session.scalars(select(WorkItem)))
        assert {(job.kind, job.payload["material_id"]) for job in jobs} == {
            ("group", ready_id), ("translate", ready_id), ("translate", blocked_id), ("translate", history_id),
        }
        assert session.scalar(select(func.count()).select_from(PaidAttempt)) == 0
        source.excerpt_allowed = False
        source.selection_threshold = 85
        session.commit()

    cli.initialize(local_live=True)
    with Session(engine) as session:
        source = session.get(Source, source_id)
        assert not source.excerpt_allowed and source.selection_threshold == 85
        assert session.scalar(select(func.count()).select_from(WorkItem)) == 4
        assert session.scalar(select(func.count()).select_from(AdminAudit).where(AdminAudit.action == "source.bootstrap")) == 2


def test_existing_local_database_restores_full_text_and_resumes_public_translation(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{(tmp_path / 'existing.db').as_posix()}")
    cli.initialize()
    engine = make_engine()
    now = now_utc()
    with Session(engine) as session:
        source = session.scalar(select(Source).where(Source.slug == "govuk"))
        source.excerpt_allowed = True
        source.selection_threshold = 85
        closed = session.scalar(select(Source).where(Source.slug == "npcc"))
        explicitly_kept_closed = session.scalar(select(Source).where(Source.slug == "europol-news"))
        session.add_all([
            AdminAudit(actor="system:launcher", action="source.bootstrap", subject="local-live-v1"),
            AdminAudit(actor="admin:local", action="source.update", subject=f"source:{closed.id}",
                       changes={"before": {"full_text_allowed": True}, "after": {"full_text_allowed": False}}),
            AdminAudit(actor="admin:local", action="source.update", subject=f"source:{explicitly_kept_closed.id}",
                       changes={"before": {"full_text_allowed": False}, "after": {"full_text_allowed": False}}),
        ])
        skipped = {"skipped": "translation_not_eligible", "role_restored": "source_role_changed",
                   "visibility_restored": "superseded"}
        for kind in (*skipped, "missing", "failed", "unselected", "withdrawn"):
            url = f"https://www.gov.uk/{kind}"
            item = Material(source_id=source.id, source_url=url, canonical_url=url, source_title=kind,
                            source_body="Original evidence. " * 35, zh_summary="公开摘要", content_hash=kind,
                            language="en", body_status="full_text", state="publication_pool", public=True,
                            relevant=True, revision=2, editorial_revision=2, timeline_kind="fresh",
                            grouping_status="complete", featured_candidate=kind != "unselected",
                            selected_at=now if kind != "unselected" else None, withdrawn=kind == "withdrawn")
            session.add(item)
            session.flush()
            if kind in skipped or kind == "failed":
                session.add(WorkItem(kind="translate", identity=f"{item.id}:2",
                                     payload={"material_id": item.id, "revision": 2}, due_at=now,
                                     status="done" if kind in skipped else "failed",
                                     result={"skipped": skipped[kind]} if kind in skipped else None,
                                     error="receipt_unknown" if kind == "failed" else None))
        session.commit()

    cli.initialize(local_live=True)
    cli.initialize(local_live=True)
    with Session(engine) as session:
        sources = {row.slug: row for row in session.scalars(select(Source))}
        assert sources["govuk"].selection_threshold == 85
        assert {slug for slug, source in sources.items() if not source.full_text_allowed} == {"npcc", "europol-news"}
        items = {item.id: item.source_title for item in session.scalars(select(Material))}
        jobs = {items[job.payload["material_id"]]: (job.status, job.error)
                for job in session.scalars(select(WorkItem).where(WorkItem.kind == "translate"))}
        assert jobs == {"skipped": ("pending", None), "missing": ("pending", None),
                        "role_restored": ("pending", None), "visibility_restored": ("pending", None),
                        "unselected": ("pending", None), "failed": ("failed", "receipt_unknown")}
        audit = session.scalar(select(AdminAudit).where(AdminAudit.subject == "local-live-full-text-v2"))
        assert audit.changes["govuk"] == {"before": False, "after": True}
        assert not {"npcc", "europol-news"} & audit.changes.keys()
        assert session.scalar(select(func.count()).select_from(PaidAttempt)) == 0


def test_local_live_database_allows_worker_commit_during_a_reader_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "concurrent.db"
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{path.as_posix()}")
    cli.initialize(local_live=True)
    reader = sqlite3.connect(path)
    writer = sqlite3.connect(path, timeout=0.2)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT count(*) FROM sources").fetchone()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE sources SET interval_minutes = 30 WHERE slug = 'govuk'")
        writer.commit()
        reader.rollback()
        assert reader.execute("SELECT interval_minutes FROM sources WHERE slug = 'govuk'").fetchone() == (30,)
    finally:
        reader.close()
        writer.close()
