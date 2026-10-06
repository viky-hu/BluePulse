from __future__ import annotations

import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

from bluepulse_backend.ingestion.lease import (
    IngestionBusy, LeaseGuard, LeaseLost, acquire_ingestion,
)
from bluepulse_backend.ingestion import lease, operations
from bluepulse_backend.ingestion.operations import recoverable_runs
from bluepulse_backend.ingestion.pipeline import run_ingestion
from bluepulse_backend.models import Base, IngestionLease, IngestionRun, Source, SourceRun


class IngestionLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        url = f"sqlite:///{(Path(self.directory.name) / 'lease.db').as_posix()}"
        self.engine = create_engine(url, connect_args={"check_same_thread": False})
        self.other_engine = create_engine(url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        self.other_engine.dispose()
        self.engine.dispose()
        self.directory.cleanup()

    def test_manual_and_schedule_share_lock_and_request_key_replays(self) -> None:
        guard = acquire_ingestion(self.engine, "manual", "npcc", "request-1")
        self.assertIsInstance(guard, LeaseGuard)
        try:
            with self.assertRaises(IngestionBusy):
                acquire_ingestion(self.other_engine, "scheduled", None, "scheduled:2026-10-06")
            replay = acquire_ingestion(self.other_engine, "manual", "npcc", "request-1")
            self.assertEqual(replay["run_id"], str(guard.run_id))
            self.assertEqual(replay["status"], "running")
            self.assertTrue(replay["idempotent_replay"])
            with self.assertRaises(ValueError):
                acquire_ingestion(self.other_engine, "manual", "another", "request-1")
        finally:
            guard.release()
        again = acquire_ingestion(self.other_engine, "manual", "npcc", "request-1")
        self.assertEqual(again["run_id"], str(guard.run_id))
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count(IngestionRun.id))), 1)

    def test_pipeline_refuses_overlap_and_reuses_completed_request(self) -> None:
        with Session(self.engine) as session, session.begin():
            session.add(Source(slug="npcc", name="NPCC", base_url="https://example.org",
                               adapter="rss", config={"allowed_hosts": ["example.org"]}))
        active = acquire_ingestion(self.engine, "scheduled", None, "scheduled:2026-10-06")
        with patch("bluepulse_backend.ingestion.pipeline.create_database_engine",
                   return_value=self.other_engine), \
             patch("bluepulse_backend.ingestion.pipeline.fetch_source", return_value=[]) as fetch, \
             patch("bluepulse_backend.ingestion.pipeline.load_model_config", return_value=None):
            try:
                with self.assertRaises(IngestionBusy):
                    run_ingestion(source_slug="npcc", idempotency_key="manual-1")
                fetch.assert_not_called()
            finally:
                active.release()
            result = run_ingestion(source_slug="npcc", idempotency_key="manual-1")
            self.assertEqual(result["status"], "succeeded")
            replay = run_ingestion(source_slug="npcc", idempotency_key="manual-1")
            self.assertEqual(replay["run_id"], result["run_id"])
            self.assertTrue(replay["idempotent_replay"])
            self.assertEqual(fetch.call_count, 1)

    def test_expired_lease_marks_old_run_and_source_interrupted(self) -> None:
        old = acquire_ingestion(self.engine, "manual", "npcc", "old-key")
        self.assertIsInstance(old, LeaseGuard)
        old._stop.set()
        old._thread.join(timeout=5)
        with Session(self.engine) as session, session.begin():
            source = Source(slug="npcc", name="NPCC", base_url="https://example.org", adapter="rss")
            session.add(source)
            session.flush()
            session.add(SourceRun(run_id=old.run_id, source_id=source.id, status="running",
                                  started_at=datetime.now(UTC)))
            session.execute(update(IngestionLease).where(IngestionLease.id == 1)
                            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        new = acquire_ingestion(self.other_engine, "scheduled", None, "new-key")
        self.assertIsInstance(new, LeaseGuard)
        try:
            with Session(self.engine) as session:
                self.assertEqual(session.get(IngestionRun, old.run_id).status, "interrupted")
                self.assertEqual(session.scalar(select(SourceRun.status)), "interrupted")
            with Session(self.engine) as session, session.begin():
                with self.assertRaises(LeaseLost):
                    old.fence(session)
        finally:
            old.release()
            new.release()
        with Session(self.engine) as session:
            self.assertIsNone(session.get(IngestionLease, 1).owner_token)

    def test_stale_run_can_be_previewed_for_recovery(self) -> None:
        old = acquire_ingestion(self.engine, "manual", "npcc", "stale-key")
        old._stop.set()
        old._thread.join(timeout=5)
        with Session(self.engine) as session, session.begin():
            session.execute(update(IngestionLease).where(IngestionLease.id == 1)
                            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        with Session(self.engine) as session:
            rows = recoverable_runs(session)
        self.assertEqual([row["run_id"] for row in rows], [str(old.run_id)])
        replay = acquire_ingestion(self.other_engine, "manual", "npcc", "stale-key")
        self.assertEqual(replay["status"], "stale")
        self.assertTrue(replay["recovery_available"])
        with patch.object(operations, "create_database_engine", return_value=self.other_engine), \
             patch.object(operations, "run_ingestion", return_value={
                 "run_id": "recovered", "status": "succeeded", "inserted": 0,
             }) as run:
            preview = operations.recover_interrupted()
            self.assertEqual(preview["count"], 1)
            run.assert_not_called()
            result = operations.recover_interrupted(apply=True)
            self.assertEqual(result["recovered_from_run_id"], str(old.run_id))
            run.assert_called_once_with(trigger_type="recovery", source_slug="npcc",
                                        idempotency_key=f"recovery:{old.run_id}")
        old.release()

    def test_heartbeat_keeps_a_long_running_job_locked(self) -> None:
        with patch.object(lease, "LEASE_SECONDS", 1), \
             patch.object(lease, "HEARTBEAT_SECONDS", 0.1):
            guard = acquire_ingestion(self.engine, "manual", None, "long-job")
            try:
                time.sleep(1.3)
                with self.assertRaises(IngestionBusy):
                    acquire_ingestion(self.other_engine, "scheduled", None, "next-job")
            finally:
                guard.release()


if __name__ == "__main__":
    unittest.main()
