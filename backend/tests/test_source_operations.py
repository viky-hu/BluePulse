from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bluepulse_backend.ingestion import operations
from bluepulse_backend.models import Base, IngestionRun, Source, SourceRun


class SourceOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        now = datetime(2026, 10, 6, 12, tzinfo=UTC)
        with Session(self.engine) as session, session.begin():
            run = IngestionRun(trigger_type="manual", started_at=now)
            session.add(run)
            session.flush()
            for slug, enabled, history in (
                ("failed-source", True, (("succeeded", -2), ("failed", -1))),
                ("healthy-source", True, (("failed", -2), ("succeeded", -1))),
                ("partial-source", True, (("partial", -1),)),
                ("disabled-source", False, (("failed", -1),)),
                ("never-source", True, ()),
            ):
                source = Source(slug=slug, name=slug, base_url="https://example.org",
                                adapter="rss", enabled=enabled)
                session.add(source)
                session.flush()
                for status, offset in history:
                    when = now + timedelta(minutes=offset)
                    session.add(SourceRun(run_id=run.id, source_id=source.id, status=status,
                                          started_at=when, finished_at=when + timedelta(seconds=1),
                                          error_class="ConnectError" if status == "failed" else None,
                                          error_message="network error" if status == "failed" else None))

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_status_reports_latest_attempt_and_never_run(self) -> None:
        with Session(self.engine) as session:
            rows = {row["slug"]: row for row in operations.source_status(session)}
        self.assertEqual(set(rows), {"failed-source", "healthy-source", "partial-source", "never-source"})
        self.assertEqual(rows["failed-source"]["status"], "failed")
        self.assertEqual(rows["failed-source"]["error_class"], "ConnectError")
        self.assertEqual(rows["healthy-source"]["status"], "succeeded")
        self.assertEqual(rows["never-source"]["status"], "never_run")

    def test_preview_does_not_run_and_apply_only_retries_latest_failures(self) -> None:
        def read(slug=None):
            with Session(self.engine) as session:
                return operations.source_status(session, slug)

        with patch.object(operations, "get_source_status", side_effect=read), \
             patch.object(operations, "run_ingestion", return_value={
                 "status": "succeeded", "run_id": "test-run", "inserted": 2,
             }) as ingest:
            preview = operations.retry_failed_sources()
            self.assertEqual([row["slug"] for row in preview["candidates"]], ["failed-source"])
            ingest.assert_not_called()
            applied = operations.retry_failed_sources(apply=True)
            self.assertEqual(applied["count"], 1)
            failed_id = next(row["source_run_id"] for row in read() if row["slug"] == "failed-source")
            ingest.assert_called_once_with(trigger_type="retry", source_slug="failed-source",
                                           idempotency_key=f"retry:{failed_id}")

    def test_partial_requires_opt_in_and_changed_status_is_skipped(self) -> None:
        with Session(self.engine) as session:
            rows = operations.source_status(session)
        with patch.object(operations, "get_source_status", return_value=rows):
            preview = operations.retry_failed_sources(include_partial=True)
        self.assertEqual({row["slug"] for row in preview["candidates"]},
                         {"failed-source", "partial-source"})

        changed = [dict(row, status="succeeded") for row in rows if row["slug"] == "failed-source"]
        with patch.object(operations, "get_source_status", side_effect=[rows, changed]), \
             patch.object(operations, "run_ingestion") as ingest:
            applied = operations.retry_failed_sources(apply=True)
            self.assertEqual(applied["results"][0]["status"], "skipped_status_changed")
            ingest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
