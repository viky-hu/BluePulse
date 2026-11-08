"""Durable singleton work slots adapted from AIHOT jobs/queue.ts."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.orm import Session

from .editorial_models import WorkItem
from .models import uid


LEASE = timedelta(minutes=10)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@contextmanager
def serialized(engine):
    # SQLite uses a database write reservation in place of AIHOT's transaction advisory locks.
    with Session(engine, expire_on_commit=False) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield session
        session.commit()


@dataclass(frozen=True)
class Claim:
    id: str
    kind: str
    payload: dict
    token: str


def enqueue(session: Session, kind: str, identity: str, payload: dict, due: datetime) -> WorkItem:
    job = session.scalar(select(WorkItem).where(WorkItem.kind == kind, WorkItem.identity == identity))
    if job is None:
        job = WorkItem(kind=kind, identity=identity, payload=payload, due_at=due)
        session.add(job)
        session.flush()
    return job


def claim(engine, now: datetime, kinds: set[str] | None = None, run_key: str | None = None) -> Claim | None:
    with serialized(engine) as session:
        query = select(WorkItem).where(or_(
            and_(WorkItem.status == "pending", WorkItem.due_at <= now),
            and_(WorkItem.status == "running", WorkItem.expires_at <= now),
        ))
        if kinds is not None:
            query = query.where(WorkItem.kind.in_(kinds))
        if run_key is not None:
            query = query.where(WorkItem.payload["run_key"].as_string() == run_key)
        running = session.scalars(select(WorkItem).where(
            WorkItem.status == "running", WorkItem.expires_at > now))
        resources = set().union(*(_resources(job) for job in running))
        history = case((WorkItem.payload["historical"].as_boolean().is_(True), 1), else_=0)
        for job in session.scalars(query.order_by(history, WorkItem.due_at, WorkItem.id)):
            if resources & _resources(job):
                continue
            job.status, job.token, job.expires_at = "running", uid(), now + LEASE
            job.attempts += 1
            return Claim(job.id, job.kind, job.payload, job.token)
        return None


def _resources(job):
    if job.kind == "collect":
        return {("source", job.payload.get("slug"))}
    resources = set()
    if job.kind == "extract":
        resources.add(("url", job.payload["url"]))
    if material_id := job.payload.get("material_id"):
        resources.add(("material", material_id))
    if story_id := job.payload.get("story_id"):
        resources.add(("story", story_id))
    if job.kind == "group":
        # AIHOT runs grouping serially: concurrent first sightings must see the preceding fact.
        resources.add(("domain", "group"))
    return resources


def owns(session: Session, work: Claim, now: datetime) -> bool:
    job = session.get(WorkItem, work.id)
    return bool(job and job.status == "running" and job.token == work.token and
                utc(job.expires_at) > utc(now))


def heartbeat(engine, work: Claim, now: datetime) -> bool:
    with serialized(engine) as session:
        changed = session.execute(update(WorkItem).where(
            WorkItem.id == work.id, WorkItem.token == work.token, WorkItem.status == "running",
            WorkItem.expires_at > now,
        ).values(expires_at=now + LEASE))
        return changed.rowcount == 1


def finish(engine, work: Claim, now: datetime, *, result: dict | None = None,
           error: str | None = None, retry_at: datetime | None = None) -> bool:
    with serialized(engine) as session:
        if not owns(session, work, now):
            return False
        job = session.get(WorkItem, work.id)
        job.status = "pending" if retry_at else "failed" if error else "done"
        job.error, job.result, job.token, job.expires_at = error, result, None, None
        if retry_at:
            job.due_at = retry_at
        return True


def requeue(session: Session, job_id: str) -> bool:
    row = session.get(WorkItem, job_id)
    if row is None or row.status not in {"failed", "pending"}:
        return False
    row.status, row.due_at = "pending", datetime.now(UTC)
    row.error = None
    return True
