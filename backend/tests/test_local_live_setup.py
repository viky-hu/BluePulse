from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bluepulse_backend import cli
from bluepulse_backend.admin_models import AdminAudit, AdminContentOverride
from bluepulse_backend.db import make_engine
from bluepulse_backend.editorial_models import PaidAttempt, WorkItem
from bluepulse_backend.models import Material, Source


def test_local_live_bootstrap_reprojects_saved_results_once(tmp_path, monkeypatch):
    monkeypatch.setenv("BLUEPULSE_DATABASE_URL", f"sqlite:///{(tmp_path / 'local.db').as_posix()}")
    cli.initialize()
    engine = make_engine()
    with Session(engine) as session:
        source = session.scalar(select(Source).where(Source.slug == "govuk"))
        assert not source.excerpt_allowed and source.selection_threshold is None

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
        assert source.excerpt_allowed and source.selection_threshold == 60
        assert not source.full_text_allowed and not source.media_allowed and not source.syndicate_full_text_allowed
        media = session.scalar(select(Source).where(Source.slug == "statescoop-law-enforcement-tech"))
        assert media.excerpt_allowed and media.selection_threshold == 76
        other = session.scalar(select(Source).where(Source.slug == "npcc"))
        assert not other.excerpt_allowed and other.selection_threshold is None
        assert session.get(Material, ready_id).public and session.get(Material, ready_id).featured_candidate
        assert session.get(Material, blocked_id).public and not session.get(Material, blocked_id).featured_candidate
        assert session.get(Material, history_id).public and not session.get(Material, withdrawn_id).public
        jobs = list(session.scalars(select(WorkItem)))
        assert [(job.kind, job.payload["material_id"]) for job in jobs] == [("group", ready_id)]
        assert session.scalar(select(func.count()).select_from(PaidAttempt)) == 0
        source.excerpt_allowed = False
        source.selection_threshold = 85
        session.commit()

    cli.initialize(local_live=True)
    with Session(engine) as session:
        source = session.get(Source, source_id)
        assert not source.excerpt_allowed and source.selection_threshold == 85
        assert session.scalar(select(func.count()).select_from(WorkItem)) == 1
        assert session.scalar(select(func.count()).select_from(AdminAudit).where(AdminAudit.action == "source.bootstrap")) == 1
