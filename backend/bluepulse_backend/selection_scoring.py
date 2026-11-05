"""Five-axis selection scoring with two separately receipted model calls."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AnalysisAttempt, Material
from .pipeline import UnknownOutcome
from .publication import evidence_allowed


AXES = ("sig", "nov", "cred", "reson", "act")
# Initial AIHOT weights, as recorded in selection-annotation-guide v2.
WEIGHTS: dict[str, tuple[int, int, int, int, int]] = {
    "model_release": (3, 2, 2, 2, 1),
    "product_launch": (2, 2, 1, 2, 3),
    "tool_or_prompt": (1, 2, 1, 2, 4),
    "research_paper": (5, 3, 1, 0, 1),
    "industry_event": (3, 1, 2, 4, 0),
    "opinion_analysis": (1, 3, 1, 4, 1),
    "tutorial_explainer": (1, 1, 1, 3, 4),
}


@dataclass(frozen=True)
class SelectionScore:
    content_type: str
    sig: int
    nov: int
    cred: int
    reson: int
    act: int
    provider_meta: dict | None = None
    raw_response: dict | None = None

    @property
    def attention_score(self) -> int:
        weights = WEIGHTS.get(self.content_type)
        values = tuple(getattr(self, axis) for axis in AXES)
        if weights is None or any(type(value) is not int or not 0 <= value <= 10 for value in values):
            raise ValueError("invalid_selection_score")
        return sum(weight * value for weight, value in zip(weights, values))

    def saved(self) -> dict:
        return {"content_type": self.content_type,
                **{axis: getattr(self, axis) for axis in AXES},
                "attention_score": self.attention_score,
                "provider_meta": self.provider_meta,
                "raw_response": self.raw_response}

    @classmethod
    def from_saved(cls, data: dict) -> SelectionScore:
        value = cls(**{key: data[key] for key in ("content_type", *AXES)},
                    provider_meta=data.get("provider_meta"), raw_response=data.get("raw_response"))
        if value.attention_score != data.get("attention_score"):
            raise ValueError("saved_score_mismatch")
        return value


def _latest(session: Session, material: Material, version: str) -> AnalysisAttempt | None:
    return session.scalar(select(AnalysisAttempt).where(
        AnalysisAttempt.material_id == material.id,
        AnalysisAttempt.revision == material.revision,
        AnalysisAttempt.input_version == version,
    ).order_by(AnalysisAttempt.attempt.desc()).limit(1))


def process_selection(session: Session, material: Material, scorer, *, max_calls: int,
                      retry_failed: bool = False) -> dict:
    """Resume saved rounds; never resend started/unknown calls automatically."""
    if max_calls < 0:
        raise ValueError("invalid_max_calls")
    report = {"status": "pending", "calls_started": 0, "scores": []}
    if material.state not in {"publication_pool", "publication_hidden"}:
        report["status"] = "waiting_analysis"
        return report
    if not material.relevant or material.duplicate_of_id is not None or not evidence_allowed(material):
        material.featured_candidate = False
        material.selection_status = "ineligible"
        session.commit()
        report["status"] = "ineligible"
        return report
    for round_number in (1, 2):
        version = f"{scorer.selection_input_version}-r{round_number}"
        attempt = _latest(session, material, version)
        if attempt is not None and attempt.status in {"result_saved", "applied"}:
            try:
                score = SelectionScore.from_saved(attempt.result or {})
            except (KeyError, TypeError, ValueError):
                material.selection_status = "invalid_receipt"
                session.commit()
                report["status"] = "invalid_receipt"
                return report
            report["scores"].append(score.attention_score)
            continue
        if attempt is not None and attempt.status in {"started", "unknown"}:
            material.selection_status = "unknown"
            session.commit()
            report["status"] = "unknown"
            return report
        if attempt is not None and attempt.status == "failed" and not retry_failed:
            material.selection_status = "failed"
            session.commit()
            report["status"] = "failed"
            return report
        if report["calls_started"] >= max_calls:
            material.selection_status = "partial" if report["scores"] else "pending"
            session.commit()
            report["status"] = material.selection_status
            return report
        attempt_number = (session.scalar(select(func.max(AnalysisAttempt.attempt)).where(
            AnalysisAttempt.material_id == material.id,
            AnalysisAttempt.revision == material.revision,
            AnalysisAttempt.input_version == version,
        )) or 0) + 1
        attempt = AnalysisAttempt(material_id=material.id, revision=material.revision,
                                  input_version=version, attempt=attempt_number, status="started")
        session.add(attempt)
        session.commit()
        report["calls_started"] += 1
        try:
            score = scorer.score(material)
            attempt.result = score.saved()  # Also validates the axes before saving.
            attempt.status = "result_saved"
            session.commit()  # Paid result is durable before touching Material.
            report["scores"].append(score.attention_score)
        except UnknownOutcome as exc:
            attempt.status, attempt.error_code = "unknown", exc.code
            material.selection_status = "unknown"
            session.commit()
            report["status"] = "unknown"
            return report
        except Exception as exc:
            attempt.status, attempt.error_code = "failed", getattr(exc, "code", "selection_failed")
            material.selection_status = "failed"
            session.commit()
            report["status"] = "failed"
            report["stop_batch"] = bool(getattr(exc, "stop_batch", False))
            return report
    first = _latest(session, material, f"{scorer.selection_input_version}-r1")
    second = _latest(session, material, f"{scorer.selection_input_version}-r2")
    ids = [((row.result or {}).get("provider_meta") or {}).get("request_id") for row in (first, second)]
    if ids[0] and ids[0] == ids[1]:
        material.featured_candidate = False
        material.selection_status = "duplicate_response"
        session.commit()
        report["status"] = "duplicate_response"
        return report
    material.importance_score = sum(report["scores"]) // 2
    threshold = material.source.selection_threshold
    if threshold is not None and not 0 <= threshold <= 100:
        material.featured_candidate = False
        material.selection_status = "invalid_threshold"
        session.commit()
        report["status"] = "invalid_threshold"
        return report
    material.featured_candidate = bool(threshold is not None and
                                       sum(report["scores"]) >= 2 * threshold)
    material.selection_status = "complete" if threshold is not None else "uncalibrated"
    first.status = second.status = "applied"
    session.commit()
    report.update(status=material.selection_status, average=material.importance_score,
                  threshold=threshold, candidate=material.featured_candidate)
    return report
