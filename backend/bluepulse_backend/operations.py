from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AnalysisAttempt, Discovery, Material, SourceRun


def source_funnel(session: Session, run_id: str) -> dict:
    """Return a drill-down friendly snapshot; mock and real adapters share this shape."""
    run = session.get(SourceRun, run_id)
    if run is None:
        raise ValueError("run_not_found")
    discoveries = session.scalars(select(Discovery).where(Discovery.run_id == run_id)).all()
    material_ids = {item.material_id for item in discoveries if item.material_id}
    materials = session.scalars(select(Material).where(Material.id.in_(material_ids))).all() if material_ids else []
    attempts = session.scalars(select(AnalysisAttempt).where(AnalysisAttempt.material_id.in_(material_ids))).all() if material_ids else []
    return {
        "run_id": run.id, "source_id": run.source_id, "status": run.status,
        "error_code": run.error_code, "fetch_metrics": run.fetch_metrics or {},
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": round((run.finished_at - run.started_at).total_seconds(), 3)
        if run.finished_at else None,
        "candidate_count": run.candidate_count,
        "discoveries": dict(Counter(item.outcome for item in discoveries)),
        "rejections": dict(Counter(item.reason_code for item in discoveries if item.reason_code)),
        "body_status": dict(Counter(item.body_status for item in materials)),
        "analysis_status": dict(Counter(item.status for item in attempts)),
        "selection_status": dict(Counter(item.selection_status for item in materials)),
        "selection_attempts": dict(Counter(item.status for item in attempts
                                           if item.input_version.endswith(("-r1", "-r2")))),
        "current_public": sum(item.public and not item.withdrawn for item in materials),
        "materials": [{"id": item.id, "url": item.canonical_url, "state": item.state,
                       "revision": item.revision, "selection_status": item.selection_status,
                       "importance_score": item.importance_score,
                       "featured_candidate": item.featured_candidate} for item in materials],
    }
