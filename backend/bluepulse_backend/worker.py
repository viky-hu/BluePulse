"""Blue Pulse's scheduled worker and bounded, resumable integration runner."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from io import BytesIO
import json
import os
from pathlib import Path
import signal
from threading import Event, Lock, Thread
import time

import httpx
from sqlalchemy import String, and_, cast, exists, func, or_, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, joinedload

from . import editorial, grouping
from .admin_models import AdminContentOverride, AdminModelSetting
from .ccgp_source import USER_AGENT
from .collection_flow import (DETAIL_MAX_ATTEMPTS, DETAIL_RETRY, FIRST_IMPORT_LIMIT, adapt_intervals,
                              admit_page, apply_detail, detail_is_current, schedule_after_fetch,
                              schedule_due_sources, unpack)
from .db import database_url, make_engine
from .editorial_models import PaidAttempt, Story, WorkItem
from .live_model import ProviderRejected, load_local_credentials, model_listed
from .live_sources import SourceFetchError
from .model_steps import Steps, environment_models
from .models import AnalysisAttempt, AutoPublicationJob, FactGroup, FactReport, Material, Source, SourceRun, now_utc
from .pipeline import ingest
from .publication import translation_needed
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
        self._hosts_lock = Lock()
        self._hosts = {}

    def tick(self, *, schedule_daily=True):
        now = self.clock()
        if schedule_daily:
            self.schedule_daily()
        recover_receipts(self.engine, now)
        with serialized(self.engine) as session:
            if self.collect_enabled:
                self._schedule_collection(session, now)
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

    def _schedule_collection(self, session, now):
        if self.max_items is None and not self.run_key:
            schedule_due_sources(session, now, self.slugs or list(SOURCES))
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
            kinds.update(("analyze", "group", "translate", "digest"))
            if self.editions_enabled:
                kinds.add("digest_sweep")
        if self.editions_enabled:
            kinds.update(("hot", "heat", "daily", "featured"))
        return kinds

    def run_one(self, run_key=None, *, kinds=None) -> bool:
        allowed = self.allowed_kinds()
        kinds = allowed if kinds is None else allowed & kinds
        work = claim(self.engine, self.clock(), kinds, run_key=run_key)
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
            return self._collect(work) if "max_items" in work.payload else self._collect_listing(work)
        if work.kind == "extract":
            return self._extract(work)
        if work.kind in {"analyze", "group", "translate"}:
            return self._editorial(work)
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
            wait = previous[0] + max(previous[1], seconds) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                yield
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
            run = SourceRun(source_id=source.id, started_at=now, fetch_metrics={"mode": "listing"})
            session.add(run)
            session.flush()
            run_id = run.id
            cursor = dict(source.collection_cursor or {})
            first = source.collection_initialized_at is None
        code = None
        with self._source_client() as client:
            adapter = build_adapter(SOURCES[slug], client, max_items=2)
            try:
                paged = getattr(adapter, "iter_listing_pages", None)
                pages = (paged(start=cursor.get("offset", 0)) if paged else
                         [(adapter.list_candidates(first_import=first), None)])
                for items, offset in pages:
                    with serialized(self.engine) as session:
                        source = self._locked_source(session, work, slug)
                        if source is None:
                            code = "source_disabled"
                            break
                        run = session.get(SourceRun, run_id)
                        admit_page(session, source, run, items, self.clock(), cursor)
                        cursor["offset"] = offset or 0
                        source.collection_cursor = dict(cursor)
                        # Set the successful checkpoint in the same transaction as the last page.
                        if offset is None or first and len(cursor.get("imported", ())) >= FIRST_IMPORT_LIMIT:
                            source.collection_initialized_at = source.collection_initialized_at or self.clock()
                            source.collection_cursor = None
                            break
            except LeaseLost:
                raise
            except Exception as exc:
                code = getattr(exc, "code", None) or (
                    "invalid_listing" if isinstance(exc, ValueError) else type(exc).__name__)
            diagnostics = getattr(adapter, "diagnostics", {})
        with serialized(self.engine) as session:
            source = self._locked_source(session, work, slug)
            run = session.get(SourceRun, run_id)
            now = self.clock()
            if source:
                schedule_after_fetch(source, now, success=code is None)
            run.status = "failed" if code else "completed" if run.candidate_count else "no_candidates"
            run.error_code, run.finished_at = code, now
            run.fetch_metrics = {**diagnostics, **run.fetch_metrics}
            return {"run_id": run.id, "status": run.status, "error": code}

    def _extract(self, work):
        slug = work.payload["slug"]
        with serialized(self.engine) as session:
            source = self._locked_source(session, work, slug)
            if not detail_is_current(session, source, work.payload):
                return {"skipped": "superseded"}
            attempts = session.get(WorkItem, work.id).attempts
        detail, error = None, None
        try:
            with self._source_client() as client:
                adapter = build_adapter(SOURCES[slug], client, max_items=2)
                detail = adapter.fetch_detail(unpack(work.payload["candidate"]))
                if detail is None or not detail.title.strip():
                    error = "title_missing"
                    detail = None
        except SourceFetchError as exc:
            error = exc.code
        except (TypeError, ValueError):
            error = "invalid_detail"
        with serialized(self.engine) as session:
            now = self.clock()
            source = self._locked_source(session, work, slug)
            if not detail_is_current(session, source, work.payload):
                return {"skipped": "superseded"}
            if error and attempts < DETAIL_MAX_ATTEMPTS:
                row = session.get(WorkItem, work.id)
                row.status, row.error, row.due_at = "pending", error, now + DETAIL_RETRY
                row.token = row.expires_at = None
                return {"status": "retrying"}
            item = apply_detail(session, source, work.payload, detail, now)
            if item and self.budget:
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
        with self.client_factory() as client, Session(self.engine, expire_on_commit=False) as session:
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
            result = ingest(session, source, adapter, guard=guard, clock=self.clock)
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
        return settings, pins, run_key, budget

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
    db = make_url(database_url()).database
    return Path(db).resolve().with_suffix(".worker.lock") if db and db != ":memory:" else None


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
    stopping = Event()

    def stop(*_):
        stopping.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    active = [set() for _ in WORKER_LANES]
    next_tick = 0.0
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
                    if time.monotonic() >= next_tick:
                        worker.tick(schedule_daily=False)
                        if next_tick == 0:
                            _write_worker_ready(handle, config)
                            print("worker_ready", flush=True)
                        next_tick = time.monotonic() + 60
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
    config = {"collection": os.environ.get("BLUEPULSE_COLLECT_ENABLED") == "1",
              "model_budget": {name: getattr(budget, name) for name in ("minute", "hour", "day")} if budget else None}
    if args.check_config:
        print(json.dumps(config))
        return
    if args.wait_ready:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if _worker_ready(config):
                return
            time.sleep(.25)
        parser.exit(1, "worker not ready with the requested settings\n")

    with _daemon_lock() as handle:
        if handle is not None:
            _write_worker_ready(handle, None)
            _run_daemon(handle, config, budget)
        else:
            print("worker_already_running", flush=True)


if __name__ == "__main__":
    main()
