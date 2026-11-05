"""Offline-capable material pipeline. No network or paid model calls are made here."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AnalysisAttempt, Discovery, Material, MaterialRevision, MaterialTopic, Source, SourceRun, now_utc
from .material_identity import publication_clock, reconcile_title, title_key
from .publication import evidence_allowed


PUBLIC_TOPIC_SLUGS = frozenset({
    "product", "practice", "paper", "law", "embodied", "public-opinion", "low-altitude",
})
LEGACY_TOPIC_SLUGS = frozenset({
    "policing", "public-safety-tech", "artificial-intelligence", "cybersecurity",
    "research", "policy-standards", "procurement-projects",
})
TOPIC_SLUGS = PUBLIC_TOPIC_SLUGS | LEGACY_TOPIC_SLUGS
INPUT_VERSION = "mock-contract-v1"


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str
    body: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    published_date: date | None = None
    language: str = "zh"
    author: str | None = None
    body_source_url: str | None = None


class SourceAdapter(Protocol):
    def candidates(self) -> list[Candidate]: ...


@dataclass
class MockSourceAdapter:
    fixtures: list[Candidate]

    def candidates(self) -> list[Candidate]:
        return self.fixtures


@dataclass(frozen=True)
class AnalysisResult:
    relevant: bool
    title_zh: str | None
    summary_zh: str | None
    topics: tuple[str, ...]
    importance_score: int
    featured_candidate: bool = False
    body_zh: str | None = None
    provider_meta: dict | None = None


class Analyzer(Protocol):
    def analyze(self, material: Material) -> AnalysisResult: ...


@dataclass
class MockAnalyzer:
    """Fixture results are keyed by canonical URL; missing fixtures fail closed."""

    fixtures: dict[str, AnalysisResult]
    input_version: str = INPUT_VERSION

    def analyze(self, material: Material) -> AnalysisResult:
        return self.fixtures[material.canonical_url]


class UnknownOutcome(Exception):
    """A provider may have received a request, but its result was not confirmed."""

    def __init__(self, code: str = "provider_outcome_unknown"):
        super().__init__(code)
        self.code = code


def canonical_url(raw: str, allowed_hosts: list[str]) -> str:
    parts = urlsplit(raw.strip())
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme.lower() not in {"http", "https"} or not host or parts.username or parts.password:
        raise ValueError("invalid_url")
    if host not in {item.lower().rstrip(".") for item in allowed_hosts}:
        raise ValueError("host_not_allowed")
    if parts.port not in (None, 80, 443):
        raise ValueError("port_not_allowed")
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    query = urlencode(sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}))
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def _normalize(value: str | None) -> str:
    return " ".join((value or "").split())


def _content_hash(candidate: Candidate) -> str:
    payload = [_normalize(candidate.title), _normalize(candidate.body), _normalize(candidate.summary),
               candidate.published_at.isoformat() if candidate.published_at else None]
    if candidate.published_date is not None:
        payload.append(candidate.published_date.isoformat())
    if candidate.body_source_url is not None:
        payload.append(candidate.body_source_url)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def _body_status(candidate: Candidate) -> str:
    if _normalize(candidate.body):
        return "full_text"
    if _normalize(candidate.summary):
        return "abstract_only"
    return "metadata_only"


def ingest(session: Session, source: Source, adapter: SourceAdapter) -> SourceRun:
    """Persist every discovery and revision. A failed source does not poison other sources."""
    if not source.enabled:
        raise ValueError("source_disabled")
    run = SourceRun(source_id=source.id)
    session.add(run)
    session.commit()
    try:
        candidates = adapter.candidates()
    except Exception as exc:
        run.status, run.error_code, run.finished_at = "failed", getattr(exc, "code", "adapter_failed"), now_utc()
        run.fetch_metrics = dict(getattr(adapter, "diagnostics", {}))
        session.commit()
        return run
    run.candidate_count = len(candidates)
    run.fetch_metrics = dict(getattr(adapter, "diagnostics", {}))
    rejected = 0
    for candidate in candidates:
        try:
            url = canonical_url(candidate.url, source.allowed_hosts)
            if candidate.body_source_url is not None:
                canonical_url(candidate.body_source_url, source.allowed_hosts)
            if not _normalize(candidate.title):
                raise ValueError("title_missing")
            seen = now_utc()
            timeline, sort_at, safe_published = publication_clock(
                candidate.published_at, candidate.published_date, seen)
            digest = _content_hash(candidate)
            material = session.scalar(select(Material).where(Material.canonical_url == url))
            previous_title_key = material.title_key if material is not None else None
            if material is None:
                material = Material(
                    canonical_url=url, source_url=candidate.url, source_id=source.id,
                    source_title=candidate.title, title_key=title_key(candidate.title),
                    source_body=candidate.body,
                    body_source_url=candidate.body_source_url,
                    source_summary=candidate.summary, language=candidate.language,
                    published_at=safe_published, published_date=candidate.published_date,
                    published_sort_at=sort_at,
                    first_seen_at=seen, fetched_at=seen,
                    content_hash=digest, timeline_kind=timeline, body_status=_body_status(candidate),
                    translation_status="pending" if candidate.language.startswith("en") else "not_required",
                    author=candidate.author,
                )
                session.add(material)
                session.flush()
                outcome = "new"
            elif material.content_hash != digest:
                material.revision += 1
                material.content_hash = digest
                material.source_url = candidate.url
                material.source_title = candidate.title
                material.title_key = title_key(candidate.title)
                material.source_body = candidate.body
                material.body_source_url = candidate.body_source_url
                material.source_summary = candidate.summary
                material.published_at = safe_published
                material.published_date = candidate.published_date
                material.published_sort_at = sort_at
                material.fetched_at = seen
                material.body_status = _body_status(candidate)
                material.timeline_kind = timeline
                material.state = "analysis_pending"
                material.public = False
                material.featured_candidate = False
                material.selection_status = "pending"
                material.grouping_status = "pending"
                material.zh_title = material.zh_summary = material.zh_body = None
                outcome = "revised"
            else:
                outcome = "duplicate"
            if outcome != "duplicate":
                session.add(MaterialRevision(
                    material_id=material.id, revision=material.revision, content_hash=digest,
                    source_title=candidate.title, source_body=candidate.body,
                    body_source_url=candidate.body_source_url,
                    source_summary=candidate.summary, published_at=candidate.published_at,
                    published_date=candidate.published_date,
                ))
                session.flush()
                reconcile_title(session, material.title_key)
                if previous_title_key and previous_title_key != material.title_key:
                    reconcile_title(session, previous_title_key)
            session.add(Discovery(run_id=run.id, source_id=source.id, material_id=material.id,
                                  url=candidate.url, outcome=outcome))
            session.commit()
        except ValueError as exc:
            session.rollback()
            rejected += 1
            session.add(Discovery(run_id=run.id, source_id=source.id, url=candidate.url,
                                  outcome="rejected", reason_code=str(exc)))
            session.commit()
    run.status = ("partial" if rejected or run.fetch_metrics.get("detail_failed", 0)
                  else "no_candidates" if not candidates else "completed")
    run.finished_at = now_utc()
    session.commit()
    return run


def _valid_result(result: AnalysisResult) -> None:
    if not 0 <= result.importance_score <= 100:
        raise ValueError("invalid_score")
    if not set(result.topics) <= TOPIC_SLUGS:
        raise ValueError("invalid_topic")
    if result.relevant and not _normalize(result.summary_zh):
        raise ValueError("summary_missing")
    if result.relevant and not result.topics:
        raise ValueError("topic_missing")


def apply_saved_analysis(session: Session, material: Material, input_version: str = INPUT_VERSION) -> bool:
    """Apply a durable result for the current revision only; safe after process restart."""
    saved = session.scalar(select(AnalysisAttempt).where(
        AnalysisAttempt.material_id == material.id,
        AnalysisAttempt.revision == material.revision,
        AnalysisAttempt.input_version == input_version,
        AnalysisAttempt.status.in_(["result_saved", "applied"]),
    ).order_by(AnalysisAttempt.attempt.desc()).limit(1))
    if saved is None or saved.result is None:
        return False
    result = AnalysisResult(**saved.result)
    _valid_result(result)
    material.relevant = result.relevant
    material.zh_title = result.title_zh
    material.zh_summary = result.summary_zh
    material.zh_body = result.body_zh
    material.topics = list(result.topics)
    session.query(MaterialTopic).filter(MaterialTopic.material_id == material.id).delete()
    session.add_all(MaterialTopic(material_id=material.id, topic_slug=slug) for slug in result.topics)
    scored_separately = bool((result.provider_meta or {}).get("scoring_required"))
    material.importance_score = 0 if scored_separately else result.importance_score
    material.featured_candidate = bool(result.featured_candidate and result.relevant and not scored_separately)
    material.selection_status = ("pending" if result.relevant else "not_relevant") if scored_separately else "legacy"
    material.translation_status = (
        "not_required" if not material.language.startswith("en") else
        "available" if result.body_zh else "source_unavailable" if material.body_status != "full_text" else "pending"
    )
    material.public = bool(result.relevant and material.duplicate_of_id is None and
                           material.source.excerpt_allowed and
                           evidence_allowed(material) and _normalize(result.summary_zh)
                           and not material.withdrawn)
    material.state = "publication_pool" if material.public else "publication_hidden"
    if material.public and material.published_public_at is None:
        material.published_public_at = now_utc()
    saved.status = "applied"
    session.commit()
    return True


def process_pending(session: Session, analyzer: Analyzer, *, retry_failed: bool = False,
                    max_items: int | None = None, source_id: str | None = None,
                    material_id: str | None = None) -> dict[str, int]:
    states = ["analysis_pending", "analysis_failed"] if retry_failed else ["analysis_pending"]
    query = select(Material).where(Material.state.in_(states)).order_by(Material.id)
    if source_id is not None:
        query = query.where(Material.source_id == source_id)
    if material_id is not None:
        query = query.where(Material.id == material_id)
    if max_items is not None:
        if max_items < 0:
            raise ValueError("invalid_max_items")
        query = query.limit(max_items)
    materials = session.scalars(query).all()
    input_version = getattr(analyzer, "input_version", INPUT_VERSION)
    counts = {"applied": 0, "failed": 0, "unknown": 0}
    for material in materials:
        if apply_saved_analysis(session, material, input_version):
            counts["applied"] += 1
            continue
        previous_unknown = session.scalar(select(AnalysisAttempt.id).where(
            AnalysisAttempt.material_id == material.id,
            AnalysisAttempt.revision == material.revision,
            AnalysisAttempt.input_version == input_version,
            AnalysisAttempt.status.in_(["unknown", "started"]),
        ).limit(1))
        if previous_unknown:
            material.state = "receipt_unknown"
            session.commit()
            counts["unknown"] += 1
            continue
        attempt_number = (session.scalar(select(func.max(AnalysisAttempt.attempt)).where(
            AnalysisAttempt.material_id == material.id,
            AnalysisAttempt.revision == material.revision,
            AnalysisAttempt.input_version == input_version,
        )) or 0) + 1
        attempt = AnalysisAttempt(material_id=material.id, revision=material.revision,
                                  input_version=input_version, attempt=attempt_number, status="started")
        session.add(attempt)
        session.commit()
        try:
            result = analyzer.analyze(material)
            _valid_result(result)
            attempt.result = {
                "relevant": result.relevant, "title_zh": result.title_zh,
                "summary_zh": result.summary_zh, "topics": list(result.topics),
                "importance_score": result.importance_score,
                "featured_candidate": result.featured_candidate, "body_zh": result.body_zh,
                "provider_meta": result.provider_meta,
            }
            attempt.status = "result_saved"
            session.commit()  # Never re-call a provider after this point.
            apply_saved_analysis(session, material, input_version)
            counts["applied"] += 1
        except UnknownOutcome as exc:
            attempt.status, attempt.error_code = "unknown", exc.code
            material.state = "receipt_unknown"
            session.commit()
            counts["unknown"] += 1
        except Exception as exc:
            attempt.status, attempt.error_code = "failed", getattr(exc, "code", "analysis_failed")
            material.state = "analysis_failed"
            session.commit()
            counts["failed"] += 1
            if getattr(exc, "stop_batch", False):
                break
    return counts
