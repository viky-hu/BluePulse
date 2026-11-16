"""Submit reviewed batches to the existing editorial worker."""
from collections import Counter
from datetime import timedelta

from sqlalchemy import and_, case, func, or_, select

from .admin_security import audit
from .editorial import PREFILTER_VERSION
from .editorial_models import WorkItem
from .models import Material, Source
from .work_queue import enqueue


def batch(session, now, *, limit, reason=None):
    if not 1 <= limit <= 100:
        raise ValueError("recheck_batch_size_must_be_1_to_100")
    jobs = session.scalars(select(WorkItem).where(
        WorkItem.kind == "analyze",
        WorkItem.payload["recheck_version"].as_string() == PREFILTER_VERSION,
    )).all()
    submitted = {job.identity for job in jobs}
    statuses = Counter(job.status for job in jobs)
    outcomes = Counter((job.result or {}).get("recheck_outcome", "skipped")
                       for job in jobs if job.status == "done")
    active = {
        (job.payload["material_id"], job.payload["revision"])
        for job in session.scalars(select(WorkItem).where(
            WorkItem.kind == "analyze", WorkItem.status.in_(("pending", "running"))))
        if "material_id" in job.payload and "revision" in job.payload
    }
    recent = func.coalesce(Material.published_sort_at, Material.published_at, Material.first_seen_at)
    priority = case((recent >= now - timedelta(days=7), 0),
                    (and_(Source.slug == "ccgp-policing-tech", Material.backfill_reason == "collection-audit"), 1),
                    else_=2)
    rows = session.execute(select(Material.id, Material.revision, Material.source_title, Source.slug)
        .join(Source).where(
            Material.public.is_(True), Material.relevant.is_(True), Material.withdrawn.is_(False),
            Material.duplicate_of_id.is_(None),
            or_(Material.collection_state.is_(None), Material.collection_state != "pending"),
            Source.participation_mode == "editorial", Material.editorial_revision == Material.revision,
            Material.editorial_data["label"].as_string() == "PASS",
            or_(Material.editorial_data["prefilter"]["version"].as_string().is_(None),
                Material.editorial_data["prefilter"]["version"].as_string() != PREFILTER_VERSION),
        ).order_by(priority, recent.desc(), Material.id))
    remaining = 0
    candidates = []
    for identifier, revision, title, source in rows:
        identity = f"{identifier}:{revision}:relevance:{PREFILTER_VERSION}"
        if identity in submitted:
            continue
        remaining += 1
        if (identifier, revision) not in active and len(candidates) < limit:
            candidates.append((identity, {"material_id": identifier, "revision": revision,
                                          "title": title, "source": source}))
    queued = 0
    if reason is not None and not (statuses["pending"] or statuses["running"]):
        for identity, item in candidates:
            enqueue(session, "analyze", identity, {"material_id": item["material_id"],
                    "revision": item["revision"], "recheck_version": PREFILTER_VERSION}, now)
            queued += 1
        if queued:
            statuses["pending"] += queued
            audit(session, "content.relevance_recheck", "maintenance:relevance", reason=reason,
                  changes={"version": PREFILTER_VERSION, "jobs": [identity for identity, _ in candidates]})
    return {"version": PREFILTER_VERSION, "remaining": remaining - queued, "status": dict(statuses),
            "outcomes": dict(outcomes), "queued": queued, "batch": [item for _, item in candidates]}
