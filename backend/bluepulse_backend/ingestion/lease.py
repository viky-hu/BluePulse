"""Database-backed singleton lease for all ingestion entry points.

Only a lease owner may commit ingestion writes. The heartbeat uses a separate
transaction so long network/model calls do not make a live worker look stale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from bluepulse_backend.models import IngestionLease, IngestionRun, SourceRun

LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 20


class IngestionBusy(RuntimeError):
    def __init__(self, run_id: UUID | None):
        self.run_id = run_id
        super().__init__(f"Another ingestion run is active: {run_id or 'unknown'}")


class LeaseLost(RuntimeError):
    pass


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _ensure_row(engine: Engine) -> None:
    dialect = engine.dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(IngestionLease).values(id=1).on_conflict_do_nothing(index_elements=["id"])
    elif dialect == "postgresql":
        statement = pg_insert(IngestionLease).values(id=1).on_conflict_do_nothing(index_elements=["id"])
    else:
        raise RuntimeError("Ingestion lease supports SQLite and PostgreSQL only.")
    with Session(engine) as session, session.begin():
        session.execute(statement)


def _existing_run(session: Session, key: str | None, trigger_type: str,
                  source_slug: str | None) -> IngestionRun | None:
    if key is None:
        return None
    existing = session.scalar(select(IngestionRun).where(IngestionRun.idempotency_key == key))
    if existing and (existing.trigger_type != trigger_type or existing.source_slug != source_slug):
        raise ValueError("Idempotency key was already used for a different ingestion request.")
    return existing


def replay_result(run: IngestionRun, lease: IngestionLease | None) -> dict[str, object]:
    live = bool(lease and lease.run_id == run.id and lease.owner_token
                and _utc(lease.expires_at) and _utc(lease.expires_at) > datetime.now(UTC))
    status = "stale" if run.status == "running" and not live else run.status
    return {"run_id": str(run.id), "status": status, **(run.counts or {}),
            "idempotent_replay": True, "failures": [], "skips": [],
            "error_summary": run.error_summary,
            "recovery_available": status == "stale"}


def _interrupt_previous(session: Session, previous_run_id: UUID | None, now: datetime) -> None:
    if previous_run_id is None:
        return
    session.execute(
        update(IngestionRun).where(IngestionRun.id == previous_run_id,
                                   IngestionRun.status == "running")
        .values(status="interrupted", finished_at=now,
                error_summary="Ingestion lease expired before the previous run finished.")
    )
    session.execute(
        update(SourceRun).where(SourceRun.run_id == previous_run_id,
                                SourceRun.status == "running")
        .values(status="interrupted", finished_at=now, error_class="LeaseExpired",
                error_message="Previous worker stopped renewing its ingestion lease.")
    )


class LeaseGuard:
    def __init__(self, engine: Engine, owner: UUID, run_id: UUID):
        self.engine = engine
        self.owner = owner
        self.run_id = run_id
        self.last_renewed = datetime.now(UTC)
        self._stop = Event()
        self._lost = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        self._thread = Thread(target=self._heartbeat_loop, name="bluepulse-ingestion-heartbeat",
                              daemon=True)
        self._thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                with Session(self.engine) as session, session.begin():
                    self.fence(session)
            except LeaseLost:
                return
            except SQLAlchemyError:
                # A transient database error may resolve before the lease expires.
                if datetime.now(UTC) >= self.last_renewed + timedelta(seconds=LEASE_SECONDS):
                    self._lost.set()
                    return

    def check(self) -> None:
        if self._lost.is_set() or datetime.now(UTC) >= self.last_renewed + timedelta(seconds=LEASE_SECONDS):
            self._lost.set()
            raise LeaseLost("Ingestion lease was lost; refusing further writes.")

    def fence(self, session: Session) -> None:
        self.check()
        now = datetime.now(UTC)
        changed = session.execute(
            update(IngestionLease)
            .where(IngestionLease.id == 1, IngestionLease.owner_token == self.owner,
                   IngestionLease.run_id == self.run_id, IngestionLease.expires_at > now)
            .values(heartbeat_at=now, expires_at=now + timedelta(seconds=LEASE_SECONDS))
        )
        if changed.rowcount != 1:
            self._lost.set()
            raise LeaseLost("Ingestion lease was taken by another worker.")
        self.last_renewed = now

    def release(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        with Session(self.engine) as session, session.begin():
            session.execute(
                update(IngestionLease)
                .where(IngestionLease.id == 1, IngestionLease.owner_token == self.owner,
                       IngestionLease.run_id == self.run_id)
                .values(owner_token=None, run_id=None, heartbeat_at=None, expires_at=None)
            )


def acquire_ingestion(
    engine: Engine, trigger_type: str, source_slug: str | None,
    idempotency_key: str | None = None,
) -> LeaseGuard | dict[str, object]:
    if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
        raise ValueError("Idempotency key must contain 1-128 characters.")
    _ensure_row(engine)
    with Session(engine) as session:
        existing = _existing_run(session, idempotency_key, trigger_type, source_slug)
        if existing is not None:
            return replay_result(existing, session.get(IngestionLease, 1))

    now = datetime.now(UTC)
    owner = uuid4()
    busy_run_id: UUID | None = None
    try:
        with Session(engine) as session, session.begin():
            changed = session.execute(
                update(IngestionLease)
                .where(IngestionLease.id == 1,
                       or_(IngestionLease.owner_token.is_(None), IngestionLease.expires_at <= now))
                .values(owner_token=owner, heartbeat_at=now,
                        expires_at=now + timedelta(seconds=LEASE_SECONDS))
            )
            if changed.rowcount != 1:
                busy_run_id = session.scalar(select(IngestionLease.run_id).where(IngestionLease.id == 1))
            else:
                previous_run_id = session.scalar(select(IngestionLease.run_id).where(IngestionLease.id == 1))
                _interrupt_previous(session, previous_run_id, now)
                run = IngestionRun(trigger_type=trigger_type, source_slug=source_slug,
                                   idempotency_key=idempotency_key, status="running",
                                   started_at=now, counts={})
                session.add(run)
                session.flush()
                session.execute(
                    update(IngestionLease).where(IngestionLease.id == 1, IngestionLease.owner_token == owner)
                    .values(run_id=run.id)
                )
                run_id = run.id
    except IntegrityError:
        # A same-key worker may have completed between our initial lookup and lock acquisition.
        with Session(engine) as session:
            existing = _existing_run(session, idempotency_key, trigger_type, source_slug)
            if existing is not None:
                return replay_result(existing, session.get(IngestionLease, 1))
        raise
    if busy_run_id is not None or changed.rowcount != 1:
        # Another worker may have committed this same key while we waited for the lock.
        with Session(engine) as session:
            existing = _existing_run(session, idempotency_key, trigger_type, source_slug)
            if existing is not None:
                return replay_result(existing, session.get(IngestionLease, 1))
        raise IngestionBusy(busy_run_id)
    guard = LeaseGuard(engine, owner, run_id)
    guard.start()
    return guard


def interrupt_owned_run(guard: LeaseGuard, error_class: str) -> None:
    """Record unexpected aborts before releasing an otherwise healthy lease."""
    try:
        with Session(guard.engine) as session, session.begin():
            guard.fence(session)
            now = datetime.now(UTC)
            session.execute(
                update(IngestionRun).where(IngestionRun.id == guard.run_id,
                                           IngestionRun.status == "running")
                .values(status="interrupted", finished_at=now,
                        error_summary=f"Worker stopped unexpectedly: {error_class}.")
            )
            session.execute(
                update(SourceRun).where(SourceRun.run_id == guard.run_id,
                                        SourceRun.status == "running")
                .values(status="interrupted", finished_at=now, error_class=error_class)
            )
    except (LeaseLost, SQLAlchemyError):
        pass
