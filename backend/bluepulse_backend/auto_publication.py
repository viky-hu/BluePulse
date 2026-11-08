"""Enqueue and execute a bounded automatic-publication batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import make_engine
from .fact_grouping import create_confirmed_featured, create_recent_featured, group_public_materials
from .live_model import DEFAULT_MODEL_ENV, load_local_credentials, model_listed
from .models import AutoPublicationJob, now_utc
from .source_collection import SOURCES
from .source_worker import run_cycle


def enqueue_job(session: Session, *, idempotency_key: str, source_slugs: list[str] | None,
                max_items: int, max_model_calls: int) -> AutoPublicationJob:
    if not idempotency_key.strip() or len(idempotency_key) > 100 or not 1 <= max_items <= 2 or not 0 <= max_model_calls <= 50:
        raise ValueError("invalid_job_request")
    slugs = list(dict.fromkeys(list(SOURCES) if source_slugs is None else source_slugs))
    if not slugs or any(slug not in SOURCES for slug in slugs):
        raise ValueError("invalid_job_sources")
    existing = session.scalar(select(AutoPublicationJob).where(
        AutoPublicationJob.idempotency_key == idempotency_key))
    if existing:
        if (existing.source_slugs, existing.max_items, existing.max_model_calls) != (slugs, max_items, max_model_calls):
            raise ValueError("idempotency_key_reused")
        return existing
    job = AutoPublicationJob(idempotency_key=idempotency_key, source_slugs=slugs,
                             max_items=max_items, max_model_calls=max_model_calls,
                             status="pending")
    session.add(job)
    session.commit()
    return job


def claim_next_job(session: Session) -> str | None:
    pending = session.scalar(select(AutoPublicationJob.id).where(
        AutoPublicationJob.status == "pending").order_by(AutoPublicationJob.created_at,
                                                           AutoPublicationJob.id).limit(1))
    if pending is None:
        return None
    changed = session.execute(update(AutoPublicationJob).where(
        AutoPublicationJob.id == pending, AutoPublicationJob.status == "pending",
    ).values(status="running", started_at=now_utc())).rowcount
    session.commit()
    return pending if changed == 1 else None


def run_claimed_job(session: Session, job_id: str, client_factory, *, analyzer=None,
                    process_call_cap: int = 0) -> dict:
    job = session.get(AutoPublicationJob, job_id)
    if job is None or job.status != "running":
        raise ValueError("job_not_claimed")
    try:
        if job.max_model_calls and analyzer is None:
            raise ValueError("model_not_enabled")
        cycle = run_cycle(session, client_factory, source_slugs=job.source_slugs,
                          max_items=job.max_items, retry_attempts=2,
                          analyzer=analyzer, model_remaining=min(job.max_model_calls, process_call_cap),
                          include_selection=False)
        grouped = group_public_materials(session)
        featured = create_recent_featured(session)
        summary = {"collection": cycle, "grouping": grouped, "featured": featured}
        job = session.get(AutoPublicationJob, job_id)
        job.status = "completed"
        job.finished_at = now_utc()
        job.report = summary
        session.commit()
        return summary
    except Exception as exc:
        session.rollback()
        job = session.get(AutoPublicationJob, job_id)
        job.status = "failed"
        job.error_code = type(exc).__name__
        job.finished_at = now_utc()
        session.commit()
        raise


def main() -> None:
    from .receipts import Budget, recover_receipts
    from .worker import Worker, _client
    from .work_queue import serialized

    parser = argparse.ArgumentParser(description="Run one queued auto-publication job")
    parser.add_argument("--execute", action="store_true", help="required for network access")
    parser.add_argument("--database-url", required=True, help="already migrated target database")
    parser.add_argument("--allow-paid-model", action="store_true")
    parser.add_argument("--max-model-calls-total", type=int, default=0)
    parser.add_argument("--env", type=Path, default=DEFAULT_MODEL_ENV)
    args = parser.parse_args()
    if not args.execute or not 0 <= args.max_model_calls_total <= 50:
        parser.error("--execute and a 0-50 call cap are required")
    if bool(args.max_model_calls_total) != args.allow_paid_model:
        parser.error("paid model use requires both explicit switch and positive cap")
    engine = make_engine(args.database_url)
    try:
        with Session(engine) as session:
            job = session.scalar(select(AutoPublicationJob).where(
                AutoPublicationJob.status.in_(("pending", "running"))).order_by(
                AutoPublicationJob.created_at, AutoPublicationJob.id).limit(1))
            if job is None:
                print(json.dumps({"status": "idle"}))
                return
            if job.max_model_calls > args.max_model_calls_total:
                parser.error("worker model cap is lower than queued job cap")
            job_id, cap = job.id, args.max_model_calls_total
        budget = Budget(cap, cap, cap) if args.allow_paid_model else None
        if budget:
            base_url, api_key, model = load_local_credentials(args.env)
            with _client() as model_client:
                if not model_listed(model_client, base_url, api_key, model):
                    parser.error("configured model could not be verified through /models")
        worker = Worker(engine, _client, presets={"default": args.env}, budget=budget, collect_enabled=True)
        recover_receipts(engine, now_utc())
        with serialized(engine) as session:
            worker.sync_requested_batches(session, now_utc(), job_id)
        while worker.run_one(job_id):
            pass
        with serialized(engine) as session:
            worker.sync_requested_batches(session, now_utc(), job_id)
            job = session.get(AutoPublicationJob, job_id)
            result = {"job_id": job.id, "status": job.status, "report": job.report}
        if result["status"] == "completed":
            with Session(engine) as session:
                result["featured"] = create_confirmed_featured(session)
        print(json.dumps(result, ensure_ascii=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
