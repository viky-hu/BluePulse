"""Local-only inspection and deliberate retry of failed ingestion sources."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from bluepulse_backend.db import create_database_engine
from bluepulse_backend.ingestion.lease import IngestionBusy
from bluepulse_backend.ingestion.pipeline import run_ingestion
from bluepulse_backend.models import IngestionLease, IngestionRun, Source, SourceRun


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()


def source_status(session: Session, source_slug: str | None = None) -> list[dict[str, object]]:
    """Return the latest attempt of each enabled source, including sources never run."""
    query = select(Source).where(Source.enabled.is_(True))
    if source_slug:
        query = query.where(Source.slug == source_slug)
    sources = list(session.scalars(query.order_by(Source.slug)))
    result: list[dict[str, object]] = []
    for source in sources:
        latest = session.scalar(
            select(SourceRun)
            .where(SourceRun.source_id == source.id)
            .order_by(SourceRun.started_at.desc(), SourceRun.finished_at.desc(), SourceRun.id.desc())
            .limit(1)
        )
        result.append({
            "slug": source.slug,
            "name": source.name,
            "last_success_at": _timestamp(source.last_success_at),
            "status": latest.status if latest else "never_run",
            "source_run_id": str(latest.id) if latest else None,
            "started_at": _timestamp(latest.started_at) if latest else None,
            "finished_at": _timestamp(latest.finished_at) if latest else None,
            "discovered": latest.discovered_count if latest else 0,
            "inserted": latest.inserted_count if latest else 0,
            "duplicates": latest.duplicate_count if latest else 0,
            "error_class": latest.error_class if latest else None,
            "error_message": latest.error_message if latest else None,
        })
    return result


def get_source_status(source_slug: str | None = None) -> list[dict[str, object]]:
    engine = create_database_engine()
    try:
        with Session(engine) as session:
            return source_status(session, source_slug)
    finally:
        engine.dispose()


def retry_failed_sources(
    source_slug: str | None = None,
    *,
    apply: bool = False,
    include_partial: bool = False,
) -> dict[str, object]:
    """Preview or retry only sources whose latest attempt still needs attention.

    Each retry uses the shared ingestion lease, so it will report busy instead
    of overlapping another manual, scheduled, or recovery run.
    """
    eligible = {"failed", "partial"} if include_partial else {"failed"}
    snapshot = get_source_status(source_slug)
    if source_slug and not snapshot:
        raise ValueError(f"No enabled source with slug: {source_slug}")
    candidates = [row for row in snapshot if row["status"] in eligible]
    if not apply:
        return {"mode": "preview", "eligible_statuses": sorted(eligible),
                "candidates": candidates, "count": len(candidates)}

    results: list[dict[str, object]] = []
    for candidate in candidates:
        slug = str(candidate["slug"])
        # Recheck immediately before each run so a changed status is not retried.
        current = get_source_status(slug)
        if not current or current[0]["status"] not in eligible:
            results.append({"source": slug, "status": "skipped_status_changed"})
            continue
        try:
            run = run_ingestion(trigger_type="retry", source_slug=slug,
                                idempotency_key=f"retry:{current[0]['source_run_id']}")
            results.append({"source": slug, "status": run["status"],
                            "run_id": run["run_id"], "inserted": run["inserted"],
                            "failures": run.get("failures", []), "skips": run.get("skips", [])})
        except IngestionBusy as exc:
            results.append({"source": slug, "status": "busy", "active_run_id": str(exc.run_id)})
            break
        except Exception as exc:
            results.append({"source": slug, "status": "error",
                            "error_class": type(exc).__name__, "message": str(exc)[:250]})
    return {"mode": "applied", "count": len(results), "results": results}


def recoverable_runs(session: Session) -> list[dict[str, object]]:
    """Find unfinished runs that no longer hold a live lease."""
    lease = session.get(IngestionLease, 1)
    now = datetime.now(UTC)
    active_run_id = (
        lease.run_id if lease and lease.owner_token and lease.expires_at
        and (lease.expires_at.replace(tzinfo=UTC) if lease.expires_at.tzinfo is None
             else lease.expires_at.astimezone(UTC)) > now else None
    )
    rows = list(session.scalars(
        select(IngestionRun).where(IngestionRun.status.in_(["interrupted", "running"]))
        .order_by(IngestionRun.started_at.desc()).limit(50)
    ))
    results: list[dict[str, object]] = []
    for run in rows:
        if run.id == active_run_id:
            continue
        key = f"recovery:{run.id}"
        if session.scalar(select(IngestionRun.id).where(IngestionRun.idempotency_key == key)):
            continue
        results.append({"run_id": str(run.id), "status": run.status,
                        "source_slug": run.source_slug, "started_at": _timestamp(run.started_at)})
    return results


def recover_interrupted(*, apply: bool = False) -> dict[str, object]:
    engine = create_database_engine()
    try:
        with Session(engine) as session:
            candidates = recoverable_runs(session)
    finally:
        engine.dispose()
    if not apply:
        return {"mode": "preview", "candidates": candidates, "count": len(candidates)}
    if not candidates:
        return {"mode": "applied", "count": 0, "results": []}
    # One recovery per invocation. Rerun the same scope; canonical URLs remain idempotent.
    candidate = candidates[0]
    try:
        run = run_ingestion(trigger_type="recovery", source_slug=candidate["source_slug"],
                            idempotency_key=f"recovery:{candidate['run_id']}")
        return {"mode": "applied", "count": 1, "recovered_from_run_id": candidate["run_id"],
                "results": [run]}
    except IngestionBusy as exc:
        return {"mode": "applied", "count": 0, "results": [],
                "status": "busy", "active_run_id": str(exc.run_id)}
