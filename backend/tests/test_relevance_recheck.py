from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.editorial_models import WorkItem
from bluepulse_backend.models import Material, Source


def test_recheck_preview_prioritizes_recent_and_procurement_backfill_without_requeue(tmp_path):
    from bluepulse_backend.relevance_recheck import batch

    now = datetime.now(UTC)
    engine = make_engine(f"sqlite:///{tmp_path / 'recheck.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        general = Source(slug="general", name="General", allowed_hosts=["example.test"])
        tenders = Source(slug="ccgp-policing-tech", name="Tenders", allowed_hosts=["example.test"])
        for name, source, age, label, reason in (
            ("old", general, 20, "PASS", None),
            ("recent", general, 1, "PASS", None),
            ("procurement", tenders, 30, "PASS", "collection-audit"),
            ("unknown", general, 0, "UNKNOWN", None),
        ):
            url = f"https://example.test/{name}"
            session.add(Material(source=source, canonical_url=url, source_url=url, source_title=name,
                                 language="en", content_hash=name, public=True, relevant=True,
                                 published_sort_at=now - timedelta(days=age), editorial_revision=1,
                                 editorial_data={"label": label}, backfill_reason=reason))
        session.commit()
        preview = batch(session, now, limit=2)
        assert [item["title"] for item in preview["batch"]] == ["recent", "procurement"]
        assert session.scalar(select(WorkItem)) is None
        submitted = batch(session, now, limit=2, reason="recheck rollout")
        assert submitted["queued"] == 2
        session.commit()
        jobs = list(session.scalars(select(WorkItem)))
        assert not any(job.payload.get("generation") for job in jobs)
        assert batch(session, now, limit=2, reason="next batch")["queued"] == 0
        for job in jobs:
            job.status = "done"
        session.commit()
        assert [item["title"] for item in batch(session, now, limit=2)["batch"]] == ["old"]
