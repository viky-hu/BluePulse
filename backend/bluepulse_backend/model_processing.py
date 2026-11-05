"""Bounded classification followed by two independent selection scores."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AnalysisAttempt, Material
from .pipeline import apply_saved_analysis, process_pending
from .publication import evidence_allowed
from .selection_scoring import process_selection


def _attempt_count(session: Session, material: Material, version: str) -> int:
    return session.scalar(select(func.count()).select_from(AnalysisAttempt).where(
        AnalysisAttempt.material_id == material.id,
        AnalysisAttempt.revision == material.revision,
        AnalysisAttempt.input_version == version,
    )) or 0


def process_model_batch(session: Session, analyzer, *, source_id: str,
                        max_calls: int, include_selection: bool = True) -> dict[str, int | bool]:
    """Count actual new paid attempts; saved results can resume at zero budget."""
    if max_calls < 0:
        raise ValueError("invalid_max_calls")
    counts: dict[str, int | bool] = {
        "applied": 0, "failed": 0, "unknown": 0, "short_body": 0,
        "score_complete": 0, "score_uncalibrated": 0, "score_partial": 0,
        "score_failed": 0, "score_unknown": 0, "score_calls": 0,
        "calls_used": 0, "stop_batch": False,
    }
    rows = session.scalars(select(Material).where(
        Material.source_id == source_id,
        Material.state.in_(["analysis_pending", "publication_pool", "publication_hidden"]),
        Material.duplicate_of_id.is_(None),
    ).order_by(Material.first_seen_at.desc(), Material.id).limit(100)).all()
    for material in rows:
        if not evidence_allowed(material):
            if material.state == "analysis_pending":
                counts["short_body"] += 1
            continue
        remaining = max_calls - int(counts["calls_used"])
        if material.state == "analysis_pending":
            version = analyzer.input_version
            before = _attempt_count(session, material, version)
            if remaining == 0:
                if not apply_saved_analysis(session, material, version):
                    continue
                outcome = {"applied": 1, "failed": 0, "unknown": 0}
            else:
                outcome = process_pending(session, analyzer, max_items=1, material_id=material.id)
            used = _attempt_count(session, material, version) - before
            counts["calls_used"] += used
            for key in ("applied", "failed", "unknown"):
                counts[key] += outcome[key]
            if outcome["failed"]:
                last = session.scalar(select(AnalysisAttempt).where(
                    AnalysisAttempt.material_id == material.id,
                    AnalysisAttempt.revision == material.revision,
                    AnalysisAttempt.input_version == version,
                ).order_by(AnalysisAttempt.attempt.desc()).limit(1))
                if last and last.error_code in {"provider_http_401", "provider_http_402",
                                                "provider_http_403", "provider_http_429"}:
                    counts["stop_batch"] = True
                    break
        if not include_selection or not material.relevant or not hasattr(analyzer, "score"):
            continue
        remaining = max_calls - int(counts["calls_used"])
        result = process_selection(session, material, analyzer, max_calls=remaining)
        counts["calls_used"] += result["calls_started"]
        counts["score_calls"] += result["calls_started"]
        key = {"complete": "score_complete", "uncalibrated": "score_uncalibrated",
               "partial": "score_partial", "failed": "score_failed",
               "invalid_receipt": "score_failed", "duplicate_response": "score_failed",
               "invalid_threshold": "score_failed",
               "unknown": "score_unknown"}.get(result["status"])
        if key:
            counts[key] += 1
        if result.get("stop_batch"):
            counts["stop_batch"] = True
            break
    return counts
