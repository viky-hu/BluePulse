"""Blue Pulse's scheduled worker and bounded, resumable integration runner."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, date, datetime, time as day_time, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
import signal
from threading import Event, Lock, Thread
import time

import httpx
from sqlalchemy import String, and_, cast, exists, func, or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, joinedload

from . import editorial, grouping
from .admin_models import AdminContentOverride, AdminModelSetting
from .ccgp_source import USER_AGENT
from .collection_flow import (DETAIL_MAX_ATTEMPTS, DETAIL_RETRY, FIRST_IMPORT_AGE, FIRST_IMPORT_LIMIT,
                              STALE_ON_DISCOVERY, adapt_intervals,
                              admission_floor, admit_page, apply_detail, detail_is_current,
                              page_precedes_floor, schedule_after_fetch, schedule_due_sources, unpack)
from .db import database_url, make_engine
from .editorial_models import PaidAttempt, Story, WorkItem
from .live_model import ProviderRejected, load_local_credentials, model_listed
from .live_sources import SourceFetchError
from .model_steps import Steps, environment_models
from .models import AnalysisAttempt, AutoPublicationJob, Discovery, FactGroup, FactReport, Material, Source, SourceRun, now_utc
from .pipeline import ingest
from .publication import translation_needed, visible
from .receipts import Budget, BudgetWait, ReceiptUnknown, recover_receipts
from .source_collection import SOURCES, build_adapter
from .source_worker import RETRYABLE
from .story_digest import DIGEST, digest_context, save_digest, schedule_digest
from .work_queue import (TRANSLATION_ELIGIBILITY_SKIPS, claim, enqueue, enqueue_translation, finish,
                         heartbeat, owns, serialized, utc)


class LeaseLost(RuntimeError):
    pass


class SourceRetry(RuntimeError):
    pass


REWRITE_SUMMARY = "rewrite_summary"
LISTING_OVERLAP = timedelta(hours=1)
SOURCE_COOLDOWN = "source_cooldown"


def _listing_error(exc):
    return getattr(exc, "code", None) or ("invalid_listing" if isinstance(exc, ValueError) else type(exc).__name__)


def _date_before(value, floor):
    if not value:
        return False
    if isinstance(value, str):
        value = date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value)
    return utc(value) < utc(floor) if isinstance(value, datetime) else value < floor.date()


def _listing_instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, day_time.min, UTC)
    return utc(value) if value else None


def _entry_progress(progress, proof, offset, floor, *, first_import_limit, legacy_boundary):
    progress["pages"] += 1
    progress["undated"] += proof.get("undated", 0)
    previous_tail = _listing_instant(progress.get("oldest_at"))
    page_head = _listing_instant(proof.get("newest_at"))
    progress["ordered"] = bool(progress.get("ordered", True) and proof.get("ordered")
                                and (not previous_tail or not page_head or page_head <= previous_tail))
    for key in ("newest_at", "oldest_at"):
        value = proof.get(key)
        if value:
            value = value if isinstance(value, str) else value.isoformat()
            previous = progress.get(key)
            progress[key] = (max if key == "newest_at" else min)(previous, value) if previous else value
    # Reaching an old boundary requires the entire raw page to predate the window.
    boundary = proof.get("oldest_at") if offset is None else proof.get("newest_at")
    passed_boundary = progress["ordered"] and _date_before(boundary, floor)
    if passed_boundary or legacy_boundary:
        reason = "publication_window"
    elif proof.get("terminal") == "exhausted" and offset is None:
        reason = "archive_exhausted"
    elif first_import_limit:
        reason = "first_import_limit"
    elif offset is None:
        reason = "archive_truncated" if proof.get("terminal") == "truncated" else "coverage_unproven"
    else:
        return False
    complete = reason in {"publication_window", "archive_exhausted"} and not progress["undated"]
    progress.update(status="complete" if complete else "partial",
                    reason="undated_listing_items" if not complete and progress["undated"] else reason)
    if reason == "archive_truncated" and progress["ordered"] and progress.get("oldest_at"):
        progress["available_from"] = progress["oldest_at"]
    return True


def _material_key(material):
    return f"{material.id}:{material.revision}"


def _queue_editorial(session, kind, material, now, run_key, generation=None):
    key = _material_key(material)
    if not run_key and not generation:
        active = session.scalar(select(WorkItem.id).where(
            WorkItem.kind == kind, WorkItem.status.in_(("pending", "running")),
            WorkItem.payload["material_id"].as_string() == material.id,
            WorkItem.payload["revision"].as_integer() == material.revision,
        ).limit(1))
        if active:
            return
    identity = ":".join(str(part) for part in (key, generation, run_key) if part is not None)
    enqueue(session, kind, identity, {"material_id": material.id, "revision": material.revision,
                                     "run_key": run_key, "generation": generation,
                                     "historical": material.timeline_kind == "historical"}, now)


def _schedule_material(session, material, now, *, run_key=None):
    if (material.duplicate_of_id or material.withdrawn or material.collection_state == "pending" or
            material.source.participation_mode == "isolated"):
        return
    if material.source.participation_mode == "hot_signal":
        if material.grouping_status == "pending":
            _queue_editorial(session, "group", material, now, run_key)
        return
    if material.editorial_revision != material.revision:
        previous_unknown = session.scalar(select(AnalysisAttempt.id).where(
            AnalysisAttempt.material_id == material.id, AnalysisAttempt.revision == material.revision,
            AnalysisAttempt.status.in_(("started", "unknown")),
        ).limit(1))
        if not previous_unknown:
            _queue_editorial(session, "analyze", material, now, run_key)
    elif material.grouping_status == "pending":
        _queue_editorial(session, "group", material, now, run_key)
    elif translation_needed(material, at=now):
        enqueue_translation(session, material, now, run_key)


class Worker:
    def __init__(self, engine, client_factory, *, presets=None, budget=None, collect_enabled=False,
                 slugs=None, run_key=None, max_items=None, clock=now_utc, editions_enabled=False):
        self.engine, self.client_factory = engine, client_factory
        self.presets = presets if presets is not None else editorial.preset_paths()
        self.budget, self.collect_enabled = budget, collect_enabled
        self.slugs, self.run_key, self.max_items = slugs, run_key, max_items
        self.clock, self.editions_enabled = clock, editions_enabled
        self.stopping = Event()
        self._hosts_lock = Lock()
        self._hosts = {}
        with Session(engine) as session:
            self._host_cooldowns = {host: utc(deadline) for host, deadline in session.execute(
                select(WorkItem.identity, WorkItem.due_at).where(WorkItem.kind == SOURCE_COOLDOWN,
                                                                 WorkItem.due_at > self.clock()))}
        from .collection_version import collection_identity
        self.collection_identity = collection_identity()

    def tick(self, *, schedule_daily=True, recover_collection=False):
        now = self.clock()
        if schedule_daily:
            self.schedule_daily()
        recover_receipts(self.engine, now)
        with serialized(self.engine) as session:
            if self.collect_enabled:
                self._schedule_collection(session, now, recover=recover_collection)
                if not self.run_key:
                    self.sync_requested_batches(session, now)
                    if self.max_items is None:
                        adapt_intervals(session, now, self.slugs or list(SOURCES))
            if self.budget:
                materials = self._sweep_query()
                if self.slugs:
                    materials = materials.where(Source.slug.in_(self.slugs))
                for material in session.scalars(materials):
                    _schedule_material(session, material, now, run_key=self.run_key)
            if self.editions_enabled:
                self._schedule_editions(session, now)

    def _sweep_query(self):
        identity = Material.id + ":" + cast(Material.revision, String)
        if self.run_key:
            identity = identity + ":" + self.run_key

        def available(kind):
            matching_identity = WorkItem.identity == identity
            if kind == "translate":
                matching_identity = and_(matching_identity, or_(
                    WorkItem.status != "done",
                    func.coalesce(WorkItem.result["skipped"].as_string(), "").not_in(TRANSLATION_ELIGIBILITY_SKIPS),
                ))
            return ~exists().where(WorkItem.kind == kind, or_(
                matching_identity,
                and_(WorkItem.status.in_(("pending", "running")),
                     WorkItem.payload["material_id"].as_string() == Material.id,
                     WorkItem.payload["revision"].as_integer() == Material.revision),
            ))

        current = Material.editorial_revision == Material.revision
        now = self.clock()
        legacy_unknown = exists().where(
            AnalysisAttempt.material_id == Material.id, AnalysisAttempt.revision == Material.revision,
            AnalysisAttempt.status.in_(("started", "unknown")),
        )
        return select(Material).join(Source).where(
            Material.withdrawn.is_(False), Material.duplicate_of_id.is_(None),
            or_(Material.collection_state.is_(None), Material.collection_state != "pending"),
            or_(
                and_(Source.participation_mode == "hot_signal", Material.grouping_status == "pending", available("group")),
                and_(Source.participation_mode == "editorial", or_(
                    and_(or_(Material.editorial_revision.is_(None), ~current), ~legacy_unknown, available("analyze")),
                    and_(current, Material.grouping_status == "pending", available("group")),
                    and_(current, Material.public.is_(True), Material.featured_candidate.is_(True),
                         Material.selected_at <= now,
                         or_(Material.visible_after.is_(None), Material.visible_after <= now),
                         Material.timeline_kind == "fresh", Material.grouping_status == "complete",
                         Material.grouping_value.is_not(False), Material.body_status == "full_text",
                         Source.excerpt_allowed.is_(True), Source.full_text_allowed.is_(True),
                         ~func.lower(Material.language).startswith("zh"),
                         or_(Material.translation_revision.is_(None),
                             Material.translation_revision != Material.revision),
                         available("translate")),
                )),
            ),
        ).order_by(Material.timeline_kind == "historical", Material.first_seen_at, Material.id).limit(300)

    def _schedule_collection(self, session, now, *, recover=False):
        if self.max_items is None and not self.run_key:
            schedule_due_sources(session, now, self.slugs or list(SOURCES), recover=recover)
            return
        for source in session.scalars(select(Source).where(Source.enabled.is_(True))):
            if source.slug not in SOURCES or self.slugs and source.slug not in self.slugs:
                continue
            if self.run_key:
                identity = f"{source.slug}:{self.run_key}"
            else:
                # A single interval slot survives scheduler restarts. Resource claims prevent overlaps.
                interval = max(60, source.interval_minutes * 60)
                identity = f"{source.slug}:{int(now.timestamp()) // interval}"
            enqueue(session, "collect", identity, {"slug": source.slug, "run_key": self.run_key,
                    "max_items": self.max_items}, now)

    def sync_requested_batches(self, session, now, batch_id=None):
        query = select(AutoPublicationJob).where(AutoPublicationJob.status.in_(("pending", "running")))
        if batch_id:
            query = query.where(AutoPublicationJob.id == batch_id)
        batches = session.scalars(query).all()
        for batch in batches:
            items = session.scalars(select(WorkItem).where(
                WorkItem.payload["run_key"].as_string() == batch.id)).all()
            if batch.status == "pending" or not items:
                if batch.max_model_calls and self.budget is None:
                    continue
                batch.started_at, batch.status = now, "running"
                for slug in batch.source_slugs:
                    enqueue(session, "collect", f"{slug}:{batch.id}", {
                        "slug": slug, "max_items": batch.max_items, "run_key": batch.id,
                        "max_model_calls": batch.max_model_calls,
                    }, now)
            if items and all(item.status in {"done", "failed"} for item in items):
                batch.finished_at = now
                batch.status = "failed" if any(item.status == "failed" for item in items) else "completed"
                batch.report = {"jobs": [{"kind": item.kind, "status": item.status,
                                          "error": item.error, "result": item.result} for item in items]}

    @staticmethod
    def _schedule_editions(session, now):
        epoch = int(now.timestamp())
        for kind, seconds in (("hot", 300), ("heat", 3600), ("featured", 300)):
            enqueue(session, kind, str(epoch // seconds), {}, now)
        enqueue(session, "digest_sweep", str(epoch // 300), {}, now)

    def schedule_daily(self, *, startup=False):
        if not self.editions_enabled:
            return
        now = self.clock()
        with serialized(self.engine) as session:
            job = enqueue(session, "daily", str(int(now.timestamp()) // 1800), {}, now)
            if startup and job.status in {"done", "failed"}:
                enqueue(session, "daily", f"startup:{now.isoformat()}", {}, now)

    @contextmanager
    def _heartbeat(self, work):
        stop = Event()

        def keep_alive():
            while not stop.wait(25):
                if not heartbeat(self.engine, work, self.clock()):
                    return

        thread = Thread(target=keep_alive, name="pulse-job-heartbeat", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join()

    def allowed_kinds(self):
        kinds = set()
        if self.collect_enabled:
            kinds.update(("collect", "extract"))
        if self.budget:
            kinds.update(("analyze", "group", "translate", "digest", REWRITE_SUMMARY))
            if self.editions_enabled:
                kinds.add("digest_sweep")
        if self.editions_enabled:
            kinds.update(("hot", "heat", "daily", "featured"))
        return kinds

    def run_one(self, run_key=None, *, kinds=None, preview=None) -> bool:
        allowed = self.allowed_kinds()
        kinds = allowed if kinds is None else allowed & kinds
        if preview is None:
            kinds = kinds - {REWRITE_SUMMARY}
        work = claim(self.engine, self.clock(), kinds, run_key=run_key, preview=preview)
        if work is None:
            return False
        try:
            with self._heartbeat(work):
                result = self._execute(work)
            if work.kind == "daily":
                result["finishedAt"] = self.clock().isoformat()
            error = "daily_compose_failed" if work.kind == "daily" and result["failed"] else None
            finish(self.engine, work, self.clock(), result=result, error=error)
        except LeaseLost:
            pass
        except BudgetWait as exc:
            if str(exc) == "request_budget_total":
                finish(self.engine, work, self.clock(), error=str(exc))
            else:
                finish(self.engine, work, self.clock(), error=str(exc),
                       retry_at=self.clock() + timedelta(seconds=exc.retry_after))
        except ReceiptUnknown:
            finish(self.engine, work, self.clock(), error="receipt_unknown",
                   retry_at=self.clock() + timedelta(minutes=5))
        except (SourceRetry, ProviderRejected) as exc:
            error = getattr(exc, "code", str(exc))
            with Session(self.engine) as session:
                attempts = session.get(WorkItem, work.id).attempts
            retry = (isinstance(exc, SourceRetry) or
                     (isinstance(exc, ProviderRejected) and
                      (error == "provider_http_429" or error.startswith("provider_http_5")))) and attempts < 3
            finish(self.engine, work, self.clock(), error=error,
                   retry_at=self.clock() + timedelta(seconds=60 * attempts) if retry else None)
        except Exception as exc:
            safe_error = (str(exc) if isinstance(exc, ValueError) and
                          str(exc).isascii() and str(exc).replace("_", "").isalnum() else type(exc).__name__)
            finish(self.engine, work, self.clock(), error=safe_error)
        return True

    def _execute(self, work):
        if work.kind == "collect":
            if "audit_items" in work.payload:
                return self._collect_historical(work)
            return self._collect(work) if "max_items" in work.payload else self._collect_listing(work)
        if work.kind == "extract":
            return self._extract(work)
        if work.kind in {"analyze", "group", "translate"}:
            return self._editorial(work)
        if work.kind == REWRITE_SUMMARY:
            return self._rewrite_summary(work)
        if work.kind == "digest":
            return self._digest(work)
        if work.kind == "digest_sweep":
            with serialized(self.engine) as session:
                now = self.clock()
                if not owns(session, work, now):
                    raise LeaseLost()
                for story_id in session.scalars(select(Story.id).where(
                    Story.merged_into_id.is_(None), Story.created_at >= now - timedelta(days=14),
                )):
                    schedule_digest(session, story_id, now, self.run_key)
                return {"checked": True}
        from .daily_reports import compose_due_reports
        from .fact_grouping import create_confirmed_featured
        from .hotspots import compute_hot_ranking, snapshot_heat

        if work.kind == "daily":
            started = self.clock()
            with Session(self.engine) as session:
                previous = session.scalar(select(WorkItem.result).where(
                    WorkItem.kind == "daily", WorkItem.status.in_(("done", "failed")), WorkItem.result.is_not(None),
                ).order_by(WorkItem.due_at.desc(), WorkItem.id).limit(1))
                retry_from = min((previous or {}).get("failed", []), default=None)
                return {"startedAt": started.isoformat(), **compose_due_reports(session, started, retry_from=retry_from)}
        handler = {"hot": compute_hot_ranking, "heat": snapshot_heat,
                   "featured": lambda session, now: create_confirmed_featured(session, now=now)}[work.kind]
        with Session(self.engine) as session:
            return handler(session, self.clock())

    @contextmanager
    def _pace_host(self, hostname, seconds):
        with self._hosts_lock:
            gate, previous = self._hosts.setdefault(hostname, (Lock(), [0.0, 0.0]))
        with gate:
            with self._hosts_lock:
                now = utc(self.clock())
                cooldown = (self._host_cooldowns.get(hostname, now) - now).total_seconds()
            if cooldown > 0:
                raise SourceFetchError("http_429", retry_after_seconds=int(cooldown + .999999))
            wait = previous[0] + max(previous[1], seconds) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                yield
            except SourceFetchError as exc:
                if delay := getattr(exc, "retry_after_seconds", None):
                    deadline = utc(self.clock()) + timedelta(seconds=delay)
                    with self._hosts_lock:
                        self._host_cooldowns[hostname] = deadline
                    with serialized(self.engine) as session:
                        hold = enqueue(session, SOURCE_COOLDOWN, hostname, {}, deadline)
                        hold.status, hold.due_at = "done", deadline
                raise
            finally:
                previous[:] = [time.monotonic(), seconds]

    @contextmanager
    def _source_client(self):
        with self.client_factory() as client:
            client.pulse_host_pace = self._pace_host
            yield client

    def _locked_source(self, session, work, slug):
        if not owns(session, work, self.clock()):
            raise LeaseLost()
        source = session.scalar(select(Source).where(Source.slug == slug))
        if source and source.allowed_hosts != [SOURCES[slug].host]:
            raise ValueError("source_host_policy_mismatch")
        return source if source and source.enabled else None

    def _collect_listing(self, work):
        slug = work.payload["slug"]
        with serialized(self.engine) as session:
            source = self._locked_source(session, work, slug)
            if source is None:
                return {"skipped": "source_disabled"}
            now = self.clock()
            session.execute(update(SourceRun).where(SourceRun.source_id == source.id, SourceRun.status == "running")
                            .values(status="failed", error_code="worker_interrupted", finished_at=now))
            run = SourceRun(source_id=source.id, started_at=now,
                            fetch_metrics={"mode": "listing", **self.collection_identity})
            session.add(run)
            session.flush()
            run_id = run.id
            state = dict(source.collection_cursor or {})
            if any(state.get(key) != value for key, value in self.collection_identity.items()):
                state = {key: state[key] for key in ("imported", "checkpoints", "observed", "gaps") if key in state}
            state.update(self.collection_identity)
            for key in ("entries", "checkpoints", "observed", "gaps", "floors"):
                state.setdefault(key, {})
            state.setdefault("imported", [])
            state.setdefault("window_end", now.isoformat())
            admission = admission_floor(source)
            end = datetime.fromisoformat(state["window_end"])
            if state["entries"] and now - end >= timedelta(minutes=source.interval_minutes):
                # A persistent failure in one entry must not suspend healthy siblings.
                for entry in state["entries"]:
                    state["floors"].pop(entry, None)
                state["entries"] = {}
                state["window_end"] = now.isoformat()
                end = now

        code, retry_after = None, 0
        results = {}
        with self._source_client() as client:
            adapter = build_adapter(SOURCES[slug], client, max_items=2)
            named = getattr(adapter, "iter_entry_pages", None)
            entries = adapter.listing_entries if named else {"default": None}
            supplemental = getattr(adapter, "supplemental_entries", frozenset())
            for entry in entries:
                if entry in state["entries"]:
                    results[entry] = {**state["entries"][entry], "reused": True}
                    continue
                previous = state["observed"].get(entry) or state["checkpoints"].get(entry)
                recent = end - (STALE_ON_DISCOVERY if admission else FIRST_IMPORT_AGE)
                floor = datetime.fromisoformat(previous) - LISTING_OVERLAP if previous else recent
                start = max(admission, floor) if admission else floor
                window_start = state["floors"].setdefault(entry, start.isoformat())
                progress = {"status": "partial", "reason": "worker_interrupted",
                            "window_start": window_start, "window_end": state["window_end"], "pages": 0, "undated": 0}
                if entry in supplemental:
                    progress["supplemental"] = True
                try:
                    self._collect_entry(work, run_id, adapter, entry, progress, state, results, admission)
                except LeaseLost:
                    raise
                except Exception as exc:
                    error = _listing_error(exc)
                    code = code or error
                    retry_after = max(retry_after, getattr(exc, "retry_after_seconds", 0) or 0)
                    progress.update(status="failed", reason=error)
                results[entry] = progress
            diagnostics = getattr(adapter, "diagnostics", {})

        with serialized(self.engine) as session:
            source = self._locked_source(session, work, slug)
            run = session.get(SourceRun, run_id)
            now = self.clock()
            required = [p for name, p in results.items() if name not in supplemental]
            coverage = ("complete" if not code and required and all(p["status"] == "complete" for p in required)
                        else "partial")
            if source:
                if not code:
                    source.collection_initialized_at = source.collection_initialized_at or now
                    for key in ("entries", "window_end", "imported"):
                        state.pop(key)
                    state["floors"] = {entry: state["floors"][entry] for entry, result in results.items()
                                       if admission and result["status"] != "complete" and not result.get("available_from")}
                source.collection_cursor = state
                schedule_after_fetch(source, now, success=code is None, error=code, retry_after=retry_after)
            run.status = "failed" if code else "completed" if run.candidate_count else "no_candidates"
            run.error_code, run.finished_at = code, now
            run.fetch_metrics = {**diagnostics, **run.fetch_metrics, "coverage": coverage,
                                 "entries": results, "coverage_gaps": state["gaps"]}
            return {"run_id": run.id, "status": run.status, "error": code, "coverage": coverage}

    def _collect_entry(self, work, run_id, adapter, entry, progress, state, results, admission):
        if self.stopping.is_set():
            raise SourceFetchError("worker_interrupted")
        named = getattr(adapter, "iter_entry_pages", None)
        paged = getattr(adapter, "iter_listing_pages", None)
        # Replaying mutable offsets from the head is safe after each page's durable writes.
        if named:
            pages = named(entry, start=0)
        elif paged:
            pages = paged(start=0)
        else:
            pages = [(adapter.list_candidates(first_import=admission is None), None)]
        iterator = iter(pages)
        start = datetime.fromisoformat(progress["window_start"])
        while not self.stopping.is_set():
            page = next(iterator, None)
            if page is None:
                raise SourceFetchError("listing_incomplete")
            items, offset = page
            proof = getattr(adapter, "listing_page_evidence", {}) or {}
            with serialized(self.engine) as session:
                source = self._locked_source(session, work, work.payload["slug"])
                if source is None:
                    raise SourceFetchError("source_disabled")
                run = session.get(SourceRun, run_id)
                admit_page(session, source, run, items, self.clock(), state)
                done = _entry_progress(progress, proof, offset, start,
                                       first_import_limit=admission is None and len(state["imported"]) >= FIRST_IMPORT_LIMIT,
                                       legacy_boundary=not named and getattr(adapter, "listing_newest_first", False)
                                       and page_precedes_floor(items, admission))
                if done and progress["status"] == "complete":
                    state["entries"][entry] = dict(progress)
                    state["checkpoints"][entry] = state["observed"][entry] = state["window_end"]
                    gap = state["gaps"].get(entry)
                    if gap and start <= datetime.fromisoformat(gap["from"]):
                        del state["gaps"][entry]
                elif done and progress.get("available_from"):
                    gap = state["gaps"].get(entry, {})
                    state["gaps"][entry] = {"from": gap.get("from", progress["window_start"]),
                                            "through": progress["available_from"], "reason": "archive_truncated"}
                    state["observed"][entry] = state["window_end"]
                source.collection_cursor = state
                run.fetch_metrics = {**run.fetch_metrics, "entries": {**results, entry: dict(progress)}}
            if done:
                return
        raise SourceFetchError("worker_interrupted")

    def _collect_historical(self, work):
        from .collection_recovery import audit_candidates

        rows = {row["url"]: row for row in work.payload["audit_items"]}
        with serialized(self.engine) as session:
            source = self._locked_source(session, work, work.payload["slug"])
            if source is None:
                return {"skipped": "source_disabled"}
            now = self.clock()
            run = SourceRun(source_id=source.id, started_at=now, finished_at=now,
                            fetch_metrics={"mode": "historical", **self.collection_identity})
            session.add(run)
            session.flush()
            # A dated amendment to a known document must not insert the entire old archive.
            known = set(session.scalars(select(Material.canonical_url).where(Material.canonical_url.in_(rows))))
            for url in tuple(rows):
                if rows[url].get("correction") and url not in known:
                    session.add(Discovery(run_id=run.id, source_id=source.id, url=url, outcome="rejected",
                                          reason_code="audit_correction_original_missing"))
                    del rows[url]
            admit_page(session, source, run, list(audit_candidates(rows.values(), source.language)), now, {},
                       audit_items=rows)
            run.status = "completed" if run.candidate_count else "no_candidates"
            return {"run_id": run.id, "status": run.status}

    def _extract(self, work):
        slug = work.payload["slug"]
        with serialized(self.engine) as session:
            source = self._locked_source(session, work, slug)
            if not detail_is_current(session, source, work.payload):
                return {"skipped": "superseded"}
            attempts = session.get(WorkItem, work.id).attempts
        detail, error, retry_after, release_at = None, None, 0, None
        try:
            with self._source_client() as client:
                adapter = build_adapter(SOURCES[slug], client, max_items=2)
                detail = adapter.fetch_detail(unpack(work.payload["candidate"]))
                if detail is None or not detail.title.strip():
                    error = "title_missing"
                    detail = None
                elif not detail.body:
                    error = "detail_body_missing"
                elif "collection_audit" in work.payload:
                    from dataclasses import replace
                    from .source_audit import window_status

                    audit = work.payload["collection_audit"]
                    listed = unpack(work.payload["candidate"])
                    if not (detail.published_at or detail.published_date):
                        detail = replace(detail, published_at=listed.published_at, published_date=listed.published_date)
                    if audit.get("correction") and not (detail.published_at or detail.published_date):
                        error = "audit_original_date_unverified"
                    dates = {key: value.isoformat() if value else None for key, value in
                             (("published_at", detail.published_at), ("published_date", detail.published_date))}
                    evidence_dates = ({"published_at": audit["updated_at"]} if audit.get("correction") else dates)
                    if window_status({**audit, **evidence_dates}, audit["window_from"], audit["window_through"]) != "in_window":
                        error = "audit_detail_date_conflict"
        except SourceFetchError as exc:
            error = exc.code
            retry_after = getattr(exc, "retry_after_seconds", 0) or 0
            release_at = exc.release_at
        except (TypeError, ValueError):
            error = "invalid_detail"
        with serialized(self.engine) as session:
            now = self.clock()
            source = self._locked_source(session, work, slug)
            if not detail_is_current(session, source, work.payload):
                return {"skipped": "superseded"}
            if release_at and "collection_audit" not in work.payload:
                row = session.get(WorkItem, work.id)
                row.status, row.error, row.due_at = "pending", error, max(release_at, now + DETAIL_RETRY)
                row.token = row.expires_at = None
                for discovery in session.scalars(select(Discovery).where(
                        Discovery.run_id == work.payload["run_id"], Discovery.url == work.payload["url"])):
                    discovery.outcome, discovery.reason_code = "deferred", error
                return {"status": "deferred", "error": error}
            if error and attempts < DETAIL_MAX_ATTEMPTS:
                row = session.get(WorkItem, work.id)
                row.status, row.error = "pending", error
                row.due_at = now + max(DETAIL_RETRY, timedelta(seconds=retry_after))
                row.token = row.expires_at = None
                return {"status": "retrying"}
            if error and "collection_audit" in work.payload:
                for discovery in session.scalars(select(Discovery).where(
                        Discovery.run_id == work.payload["run_id"], Discovery.url == work.payload["url"])):
                    discovery.outcome, discovery.reason_code = "detail_unconfirmed", error
                return {"status": "unconfirmed", "material_id": work.payload["material_id"], "error": error}
            item = apply_detail(session, source, work.payload, detail, now)
            if item and self.budget:
                if detail is not None and (work.payload.get("collection_audit") or {}).get("recheck_version"):
                    job = session.scalar(select(WorkItem).where(
                        WorkItem.kind == "analyze", WorkItem.identity == _material_key(item),
                        WorkItem.status == "failed", WorkItem.error == "invalid_editorial_copy"))
                    if job is not None and item.editorial_revision != item.revision:
                        job.status, job.due_at, job.error = "pending", now, None
                _schedule_material(session, item, now)
            return {"status": item.collection_state if item else "unconfirmed",
                    "material_id": item.id if item else None, "error": error}

    def _collect(self, work):
        def guard(session):
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            if not owns(session, work, self.clock()):
                raise LeaseLost()

        slug = work.payload["slug"]
        spec = SOURCES[slug]
        with self._source_client() as client, Session(self.engine, expire_on_commit=False) as session:
            source = session.scalar(select(Source).where(Source.slug == slug))
            if source is None or not source.enabled:
                return {"skipped": "source_disabled"}
            if source.allowed_hosts != [spec.host]:
                raise ValueError("source_host_policy_mismatch")
            guard(session)
            session.execute(update(SourceRun).where(SourceRun.source_id == source.id, SourceRun.status == "running")
                            .values(status="failed", error_code="worker_interrupted", finished_at=self.clock()))
            session.commit()
            adapter = build_adapter(spec, client, max_items=work.payload.get("max_items", 2))
            result = ingest(session, source, adapter, guard=guard, clock=self.clock,
                            provenance={"mode": "bounded", **self.collection_identity})
            if result.status == "failed" and result.error_code in RETRYABLE:
                raise SourceRetry(result.error_code)
            if result.status == "failed":
                raise ValueError(result.error_code or "source_failed")
            if self.budget and work.payload.get("max_model_calls", 1):
                guard(session)
                for item in session.scalars(select(Material).where(Material.source_id == source.id)):
                    _schedule_material(session, item, self.clock(), run_key=work.payload.get("run_key"))
                session.commit()
            return {"run_id": result.id, "status": result.status, "error": result.error_code}

    def _model_configuration(self, session, work):
        job = session.get(WorkItem, work.id)
        settings, pins = job.payload.get("models"), job.payload.get("pins")
        if settings is None:
            settings = {**environment_models(), **{row.capability: row.model for row in
                        session.scalars(select(AdminModelSetting))}}
            capabilities = {
                "analyze": ("prefilter", "score", "structure", "understand", "summarize"),
                "group": ("group", "groupReview"),
                "translate": ("translate",), "digest": ("digest",),
                REWRITE_SUMMARY: ("understand", "summarize"),
            }[work.kind]
            aliases = {settings.get(capability, "default") for capability in capabilities}
            if work.kind == "group" and "embedding" in settings:
                aliases.add(settings["embedding"])
            pins = {}
            for alias in aliases:
                base, _, model = load_local_credentials(self.presets[alias])
                pins[alias] = editorial.input_hash(json.dumps([base, model]))
            job.payload = {**job.payload, "models": settings, "pins": pins}
        run_key = work.payload.get("run_key") or self.run_key
        budget = self.budget
        batch = session.get(AutoPublicationJob, run_key) if run_key else None
        if batch:
            budget = Budget(budget.minute, budget.hour, budget.day, batch.max_model_calls)
        if work.kind == REWRITE_SUMMARY:
            budget = Budget(budget.minute, budget.hour, budget.day, work.payload["max_attempts"])
        return settings, pins, run_key, budget

    def _rewrite_summary(self, work):
        from .daily_reports import correct_article_summary
        from .reading import can_show_reading_value
        from .summary_backfill import has_manual_summary

        payload = work.payload
        material_id, revision = payload["material_id"], payload["revision"]

        def skip(session, article, now):
            if not article or article.revision != revision or payload["copy_version"] != editorial.COPY_VERSION:
                return "superseded"
            if not visible(article, at=now) or article.collection_state == "pending":
                return "not_public"
            if has_manual_summary(session, article.id):
                return "manual_summary"
            if (article.editorial_data or {}).get("copy_version") == editorial.COPY_VERSION:
                return "already_current"
            return None

        with serialized(self.engine) as session:
            now = self.clock()
            if not owns(session, work, now):
                raise LeaseLost()
            article = session.get(Material, material_id, options=[joinedload(Material.source)])
            if reason := skip(session, article, now):
                return {"skipped": reason}
            previous_summary = article.zh_summary
            previous_editorial = article.editorial_data
            inputs = editorial.rewrite_input(article)
            input_hash = editorial.input_hash(json.dumps(inputs, ensure_ascii=False, sort_keys=True))
            reviewed = payload.get("reviewed_copy")
            if reviewed and reviewed.get("input_hash") != input_hash:
                return {"skipped": "copy_changed"}
            with_reason = can_show_reading_value(session, article, at=now)
            if reviewed and with_reason and not reviewed.get("with_reason", payload.get("with_reason")):
                reviewed = None
            if not reviewed:
                settings, pins, run_key, budget = self._model_configuration(session, work)
        if reviewed:
            summary, reason = reviewed["summary"], reviewed["reason"]
        else:
            with self.client_factory() as client:
                step = Steps(self.engine, client, self.presets, settings, f"article:{material_id}:{revision}",
                             budget, run_key, self.clock, pins=pins)
                summary, reason = editorial.rewrite_summary(inputs, step, with_reason=with_reason,
                                                            repair=bool(payload.get("repair")))
        with serialized(self.engine) as session:
            now = self.clock()
            if not owns(session, work, now):
                raise LeaseLost()
            current = session.get(Material, material_id)
            if skipped := skip(session, current, now):
                return {"skipped": skipped}
            if current.zh_summary != previous_summary or current.editorial_data != previous_editorial:
                return {"skipped": "copy_changed"}
            if payload["preview"]:
                return {"preview": True, "summary": summary, "reason": reason, "input_hash": input_hash,
                        "with_reason": with_reason}
            is_representative = can_show_reading_value(session, current, at=now)
            editorial.save_summary_copy(current, summary, reason if is_representative else None)
            correct_article_summary(session, current, now)
            return {"material_id": material_id, "revision": revision}

    def _digest(self, work):
        story_id, key = work.payload["story_id"], work.payload["input_hash"]
        with serialized(self.engine) as session:
            current, reports = digest_context(session, story_id, self.clock())
            if current != key or len(reports) < 2:
                schedule_digest(session, story_id, self.clock(), work.payload.get("run_key"))
                return {"skipped": "evidence_changed"}
            settings, pins, run_key, budget = self._model_configuration(session, work)
        with self.client_factory() as client:
            step = Steps(self.engine, client, self.presets, settings, f"story:{story_id}",
                         budget, run_key, self.clock, pins=pins)
            output, _ = step("digest", "digest", DIGEST, {"reports": reports}, 1200)
        digest = output.get("digest")
        if not isinstance(digest, str) or not 10 <= len(digest.strip()) <= 2000:
            raise ValueError("invalid_story_digest")
        with serialized(self.engine) as session:
            if not owns(session, work, self.clock()):
                raise LeaseLost()
            saved = save_digest(session, story_id, key, digest.strip(), self.clock())
            if not saved:
                schedule_digest(session, story_id, self.clock(), run_key)
            return {"story_id": story_id, "saved": saved}

    def _editorial(self, work):
        payload = work.payload
        material_id, revision = payload["material_id"], payload["revision"]
        generation = payload.get("generation")
        with serialized(self.engine) as session:
            item = session.get(Material, material_id, options=[joinedload(Material.source)])
            if not item or item.revision != revision or item.withdrawn or item.duplicate_of_id or item.collection_state == "pending":
                return {"skipped": "superseded"}
            source_mode = item.source.participation_mode
            if source_mode == "isolated" or source_mode == "hot_signal" and work.kind != "group":
                return {"skipped": "source_role"}
            settings, pins, run_key, budget = self._model_configuration(session, work)
            threshold = item.source.selection_threshold
            analysis_generation = (item.editorial_data or {}).get("generation")
        subject = f"article:{material_id}:{revision}"
        with self.client_factory() as client:
            step = Steps(self.engine, client, self.presets, settings, subject, budget, run_key,
                         self.clock, generation=generation, pins=pins)
            if work.kind == "analyze":
                result = editorial.analyze(item, step)
            elif work.kind == "group":
                if item.editorial_revision != revision and source_mode != "hot_signal":
                    return {"skipped": "analysis_not_current"}
                with Session(self.engine) as session:
                    candidates = grouping.recall(session, item, self.clock(),
                                                  step.embeddings if "embedding" in settings else None)
                result = grouping.decide(item, candidates, step)
            else:
                if not translation_needed(item, at=self.clock(), replace_current=generation is not None):
                    return {"skipped": "translation_not_eligible"}
                result = editorial.translate(item.source_body, step)
        with serialized(self.engine) as session:
            now = self.clock()
            if not owns(session, work, now):
                raise LeaseLost()
            current = session.get(Material, material_id)
            if current is None or current.revision != revision or current.withdrawn or current.duplicate_of_id:
                return {"skipped": "superseded"}
            if current.source.participation_mode != source_mode:
                return {"skipped": "source_role_changed"}
            override = session.get(AdminContentOverride, material_id)
            fields = override.fields if override else {}
            if work.kind == "analyze":
                if current.source.selection_threshold != threshold:
                    # The scores were independent of the threshold. Reuse them on the next run.
                    raise ValueError("selection_threshold_changed")
                editorial.apply_analysis(session, current, result, now, fields)
                current.editorial_data = {**current.editorial_data, "generation": generation}
                _queue_editorial(session, "group", current, now, run_key, generation)
            elif work.kind == "group":
                if (current.editorial_data or {}).get("generation") != analysis_generation:
                    return {"skipped": "analysis_changed"}
                grouping.apply_grouping(session, current, result, now, fields)
                session.flush()
                member = session.get(FactReport, current.id)
                if member:
                    fact = session.get(FactGroup, member.fact_id)
                    if fact:
                        schedule_digest(session, fact.story_id, now, run_key)
            else:
                if not translation_needed(current, at=now, replace_current=generation is not None):
                    return {"skipped": "translation_not_eligible"}
                current.zh_body, complete = result
                current.translation_revision = revision
                current.translation_status = "available" if complete else "partial"
            _schedule_material(session, current, now, run_key=run_key)
            return {"material_id": material_id, "revision": revision}


def _client():
    return httpx.Client(timeout=httpx.Timeout(45, connect=10), follow_redirects=False,
                        headers={"User-Agent": USER_AGENT})


def _budget_from_env():
    if os.environ.get("BLUEPULSE_MODEL_CALLS_ENABLED") != "1":
        return None
    values = [int(os.environ.get(f"BLUEPULSE_MODEL_BUDGET_{name}", ""))
              for name in ("MINUTE", "HOUR", "DAY")]
    if any(value <= 0 for value in values):
        raise ValueError("invalid_model_budget")
    return Budget(*values)


def _daemon_lock_path():
    from .collection_version import sqlite_database_path

    path = sqlite_database_path(database_url())
    return path.with_suffix(".worker.lock") if path else None


@contextmanager
def _daemon_lock():
    lock = _daemon_lock_path()
    if lock is None:
        yield BytesIO(b"0")
        return
    lock.touch(exist_ok=True)
    with lock.open("r+b") as handle:
        if os.name == "nt":
            import msvcrt
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            acquire()
        except OSError:
            yield None
        else:
            yield handle


def _write_worker_ready(handle, config):
    # The first byte is the OS lock. Probes can read the status after that byte.
    handle.seek(1)
    handle.truncate()
    if config is not None:
        handle.write(json.dumps(config).encode())
    handle.flush()


def _worker_ready(config):
    path = _daemon_lock_path()
    if path is None or not path.is_file():
        return False
    with _daemon_lock() as handle:
        if handle is not None:
            return False
    try:
        with path.open("rb") as active:
            active.seek(1)
            return json.load(active) == config
    except (OSError, ValueError):
        return False


WORKER_LANES = (
    ({"daily"}, 1),
    ({"collect"}, 8),
    ({"extract"}, 4),
    ({"analyze"}, 6),
    ({"group", "translate", "digest", "digest_sweep", "hot", "heat", "featured"}, 1),
)


def _dispatch(worker, executor, active):
    now = worker.clock()
    allowed = worker.allowed_kinds()
    with Session(worker.engine) as session:
        due = dict(session.execute(select(WorkItem.kind, func.count()).where(
            WorkItem.kind.in_(allowed),
            or_(and_(WorkItem.status == "pending", WorkItem.due_at <= now),
                and_(WorkItem.status == "running", WorkItem.expires_at <= now)),
        ).group_by(WorkItem.kind)).all())
    for (kinds, capacity), running in zip(WORKER_LANES, active):
        for future in tuple(running):
            if future.done():
                running.remove(future)
                try:
                    future.result()
                except OperationalError:
                    print("worker_database_temporarily_unavailable", flush=True)
        remaining = min(capacity - len(running), sum(due.get(kind, 0) for kind in kinds))
        for _ in range(remaining):
            running.add(executor.submit(worker.run_one, kinds=kinds))


def _run_daemon(handle, config, budget):
    engine = make_engine()
    worker = Worker(engine, _client, budget=budget, editions_enabled=True,
                    collect_enabled=config["collection"])
    stopping = worker.stopping

    def stop(*_):
        stopping.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    active = [set() for _ in WORKER_LANES]
    next_tick = 0.0
    last_tick = None
    daily_slot = None
    try:
        with ThreadPoolExecutor(max_workers=sum(capacity for _, capacity in WORKER_LANES)) as executor:
            while not stopping.is_set():
                try:
                    slot = int(worker.clock().timestamp()) // 1800
                    if slot != daily_slot:
                        worker.schedule_daily(startup=daily_slot is None)
                        daily_slot = slot
                        _dispatch(worker, executor, active)
                    now = worker.clock()
                    recover_collection = last_tick is None or now - last_tick > timedelta(minutes=2)
                    if recover_collection or time.monotonic() >= next_tick:
                        worker.tick(schedule_daily=False, recover_collection=recover_collection)
                        if next_tick == 0:
                            _write_worker_ready(handle, config)
                            print("worker_ready", flush=True)
                        next_tick = time.monotonic() + 60
                        last_tick = now
                    if not stopping.is_set():
                        _dispatch(worker, executor, active)
                except OperationalError:
                    print("worker_database_temporarily_unavailable", flush=True)
                stopping.wait(2)
    finally:
        _write_worker_ready(handle, None)
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live-test", type=Path, help="fixed isolated output directory, safe to resume")
    mode.add_argument("--check-config", action="store_true", help="validate local worker settings")
    mode.add_argument("--wait-ready", action="store_true", help="wait for a worker with the current settings")
    args = parser.parse_args(argv)
    from .cli import initialize

    if args.live_test:
        directory = args.live_test.resolve()
        directory.mkdir(parents=True, exist_ok=True)
        test_db = directory / "live-test.sqlite3"
        address = f"sqlite:///{test_db.as_posix()}"
        if address == database_url() or test_db.is_symlink() or test_db.exists() and test_db.stat().st_nlink != 1:
            parser.error("live-test must use an isolated database")
        manifest = directory / "run.json"
        profile = {"kind": "bluepulse_autodl_prelaunch", "max_requests": 30}
        if manifest.exists():
            if json.loads(manifest.read_text(encoding="utf-8")) != profile:
                parser.error("unrecognized live-test directory")
        elif test_db.exists():
            parser.error("refusing to use a pre-existing database without a live-test manifest")
        else:
            with manifest.open("x", encoding="utf-8") as output:
                json.dump(profile, output)
        base, key, model = load_local_credentials()
        with _client() as client:
            if not model_listed(client, base, key, model):
                parser.error("configured model could not be verified through /models")
        os.environ["BLUEPULSE_DATABASE_URL"] = address
        initialize()
        engine = make_engine(address)
        worker = Worker(engine, _client, budget=Budget(30, 30, 30, total=30),
                        collect_enabled=True, slugs=["govuk", "jiangsu-police", "ccgp-policing-tech", "htx-news"],
                        run_key="prelaunch-autodl-30", max_items=1, editions_enabled=True)
        worker.tick()
        while worker.run_one():
            pass
        with Session(engine) as session:
            report = {"requests": session.scalar(select(func.count()).select_from(PaidAttempt)),
                      "materials": session.scalar(select(func.count()).select_from(Material)),
                      "jobs": [{"kind": job.kind, "status": job.status, "error": job.error, "result": job.result}
                               for job in session.scalars(select(WorkItem))]}
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True))
        engine.dispose()
        return

    try:
        budget = _budget_from_env()
        if budget:
            load_local_credentials()
    except (OSError, ValueError):
        parser.error("check backend/.env and the three BLUEPULSE_MODEL_BUDGET_* values")
    from .collection_version import worker_configuration

    config = worker_configuration(
        collection=os.environ.get("BLUEPULSE_COLLECT_ENABLED") == "1",
        model_budget={name: getattr(budget, name) for name in ("minute", "hour", "day")} if budget else None,
        database=database_url(),
    )
    if args.check_config:
        print(json.dumps(config))
        return
    if args.wait_ready:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if _worker_ready(config):
                return
            time.sleep(.25)
        parser.exit(1, "worker not ready with the requested settings and collection version; check runtime health\n")

    with _daemon_lock() as handle:
        if handle is not None:
            _write_worker_ready(handle, None)
            _run_daemon(handle, config, budget)
        else:
            print("worker_already_running", flush=True)


if __name__ == "__main__":
    main()
