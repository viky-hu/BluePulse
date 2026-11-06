"""Dormant queue entry point: collect, classify, group, then build a recent edition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .ccgp_source import USER_AGENT
from .db import make_engine
from .fact_grouping import create_recent_featured, group_public_materials
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
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
    parser = argparse.ArgumentParser(description="Run one queued auto-publication job")
    parser.add_argument("--execute", action="store_true", help="required for network access")
    parser.add_argument("--database-url", required=True, help="already migrated target database")
    parser.add_argument("--allow-paid-model", action="store_true")
    parser.add_argument("--max-model-calls-total", type=int, default=0)
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[3] / ".env")
    args = parser.parse_args()
    if not args.execute or not 0 <= args.max_model_calls_total <= 50:
        parser.error("--execute and a 0-50 call cap are required")
    if bool(args.max_model_calls_total) != args.allow_paid_model:
        parser.error("paid model use requires both explicit switch and positive cap")
    engine = make_engine(args.database_url)
    try:
        with Session(engine) as session:
            job_id = claim_next_job(session)
            if job_id is None:
                print(json.dumps({"status": "idle"}))
                return
            job = session.get(AutoPublicationJob, job_id)
            if job.max_model_calls > args.max_model_calls_total:
                job.status = "pending"
                job.started_at = None
                session.commit()
                parser.error("worker model cap is lower than queued job cap")
        def client_factory():
            return httpx.Client(timeout=httpx.Timeout(35, connect=10),
                                follow_redirects=False, headers={"User-Agent": USER_AGENT})
        model_client = None
        analyzer = None
        try:
            if args.allow_paid_model:
                base_url, api_key, model = load_local_credentials(args.env)
                model_client = client_factory()
                if not model_listed(model_client, base_url, api_key, model):
                    raise ValueError("model_not_listed")
                analyzer = LiveAnalyzer(model_client, base_url, api_key, model)
            with Session(engine) as session:
                result = run_claimed_job(session, job_id, client_factory,
                                         analyzer=analyzer,
                                         process_call_cap=args.max_model_calls_total)
            print(json.dumps({"job_id": job_id, "status": "completed",
                              "model_used": result["collection"]["model_used"],
                              "featured": result["featured"]["selected"]}, ensure_ascii=False))
        except Exception as exc:
            with Session(engine) as session:
                job = session.get(AutoPublicationJob, job_id)
                if job is not None and job.status == "running":
                    job.status = "failed"
                    job.error_code = type(exc).__name__
                    job.finished_at = now_utc()
                    session.commit()
            raise
        finally:
            if model_client is not None:
                model_client.close()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
