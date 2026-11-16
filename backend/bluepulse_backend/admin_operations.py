from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .admin_feedback import Reason
from .admin_models import AdminContentOverride, AdminEvaluation, AdminModelSetting
from .admin_security import ACTOR, audit, begin_write
from .editorial import available_presets
from .editorial_models import PaidAttempt, PaidReceipt, WorkItem
from .models import FactGroup, FactReport, Material, MaterialTopic, Source, SourceRun, now_utc
from .pipeline import PUBLIC_TOPIC_SLUGS
from .publication import automatic_relevance_allowed, project_visibility, relevance_allowed, translation_needed
from .work_queue import enqueue, enqueue_translation, requeue


CAPABILITIES = {
    "prefilter": "行业预筛", "score": "五轴双评分", "structure": "分类和事实抽取", "understand": "内容理解",
    "summarize": "标题摘要", "group": "事件归组", "groupReview": "归组复核", "digest": "事件综述",
    "translate": "全文翻译",
}
OVERRIDE_FIELDS = {"zh_title", "zh_summary", "topics", "relevant", "selected"}


class AdminReason(Reason):
    model_config = ConfigDict(extra="forbid")


class SourcePatch(AdminReason):
    version: str = Field(pattern=r"^[0-9a-f]{64}$")
    enabled: bool | None = None
    excerpt_allowed: bool | None = None
    full_text_allowed: bool | None = None
    media_allowed: bool | None = None
    syndicate_full_text_allowed: bool | None = None
    selection_threshold: int | None = Field(default=None, ge=0, le=100)
    tier: Literal["T1", "T1_5", "T2", "EXCLUDE_MP"] | None = None
    participant_key: str | None = Field(default=None, max_length=120)
    participation_mode: Literal["editorial", "signal", "isolated"] | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    owner_entity: str | None = Field(default=None, max_length=120)
    publisher_role: Literal["organization", "person"] | None = None


class ContentOverride(AdminReason):
    zh_title: str | None = Field(default=None, min_length=1, max_length=200)
    zh_summary: str | None = Field(default=None, min_length=1, max_length=4000)
    topics: list[str] | None = Field(default=None, min_length=1, max_length=8)
    relevant: bool | None = None
    selected: bool | None = None


class Visibility(AdminReason):
    withdrawn: bool


class Rerun(AdminReason):
    step: Literal["analyze", "group", "translate"]


class Membership(AdminReason):
    fact_id: UUID | None = None
    standalone: bool = False


class Merge(AdminReason):
    from_id: UUID
    into_id: UUID


class ReceiptRelease(AdminReason):
    billed: bool


class ModelChoice(AdminReason):
    model: str | None = Field(max_length=64)


class DailyCorrection(AdminReason):
    version: int = Field(ge=1)


class EvaluationImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=160)
    report: dict


def source_view(source: Source) -> dict:
    values = {key: getattr(source, key) for key in (
        "id", "slug", "name", "region", "source_type", "enabled", "excerpt_allowed", "full_text_allowed",
        "media_allowed", "syndicate_full_text_allowed", "selection_threshold", "allowed_hosts",
        "tier", "participant_key", "participation_mode", "interval_minutes", "owner_entity", "publisher_role",
    )}
    version = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    return {**values, "version": version}


def content_view(item: Material) -> dict:
    return {key: getattr(item, key) for key in (
        "id", "revision", "source_id", "source_url", "source_title", "zh_title", "zh_summary", "topics",
        "relevant", "state", "withdrawn", "public", "importance_score", "selection_status",
        "featured_candidate", "grouping_status", "translation_status", "editorial_revision",
    )}


def admin_rerun(session: Session, item: Material, step: str, *, explicit: bool) -> WorkItem:
    now = now_utc()
    generation = uuid4().hex
    payload = {"material_id": item.id, "revision": item.revision}
    if explicit:
        payload["generation"] = generation
    if step in {"analyze", "group"}:
        item.grouping_status, item.selected_at = "pending", None
    return enqueue(session, step, f"{item.id}:{item.revision}:{generation}", payload, now)


def refresh_candidate(item: Material, fields: dict) -> bool:
    scores = (item.editorial_data or {}).get("scores", [])
    threshold = item.source.selection_threshold
    judged = item.editorial_revision == item.revision and len(scores) == 2
    qualifies = bool(judged and threshold is not None and sum(scores) >= 2 * threshold)
    before = item.featured_candidate
    item.featured_candidate = bool(relevance_allowed(item) and judged and fields.get("selected") is not False and
                                   (qualifies or fields.get("selected") is True))
    if judged:
        item.selection_status = ("qualified" if qualifies else
                                 "uncalibrated" if threshold is None else "below_threshold")
    if not item.featured_candidate:
        item.selected_at = None
    return not before and item.featured_candidate


def reproject_source(session: Session, source: Source, *, threshold_changed: bool,
                     mode_changed: bool = False, fresh_only: bool = False) -> int:
    released = 0
    items = session.scalars(select(Material).where(
        Material.source_id == source.id,
        Material.state.in_(("publication_pool", "publication_hidden")),
    )).all()
    for item in items:
        was_public = item.public
        project_visibility(item)
        released += int(not was_public and item.public)
        needs_group = mode_changed and item.editorial_revision == item.revision
        if threshold_changed:
            override = session.get(AdminContentOverride, item.id)
            needs_group = refresh_candidate(item, override.fields if override else {}) or needs_group
        newly_available = not was_public and item.public and item.featured_candidate and item.selected_at is None
        if fresh_only and (item.timeline_kind != "fresh" or not item.public):
            continue
        if needs_group or newly_available:
            admin_rerun(session, item, "group", explicit=False)
        now = now_utc()
        if translation_needed(item, at=now):
            enqueue_translation(session, item, now)
    return released


def register_operations(router: APIRouter, session_dep, guard, error) -> None:
    protected = [Depends(guard)]

    def required(session: Session, cls, identifier):
        row = session.get(cls, identifier)
        if row is None:
            raise error(404, "not_found", "记录不存在。")
        return row

    def reason(body: Reason) -> str:
        if not body.reason.strip():
            raise error(400, "invalid_request", "请填写操作原因。")
        return body.reason.strip()

    @router.patch("/admin/sources/{source_id}", dependencies=protected)
    def source_update(source_id: UUID, body: SourcePatch, session: Session = Depends(session_dep)):
        why = reason(body)
        fields = body.model_dump(exclude_unset=True, exclude={"reason", "version"})
        nullable = {"selection_threshold", "tier", "participant_key", "owner_entity", "publisher_role"}
        if not fields or any(value is None and key not in nullable for key, value in fields.items()):
            raise error(400, "invalid_request", "信源设置无效。")
        for key in ("participant_key", "owner_entity"):
            if key in fields:
                fields[key] = (fields[key] or "").strip() or None
        begin_write(session)
        source = required(session, Source, str(source_id))
        if source_view(source)["version"] != body.version:
            raise error(409, "conflict", "信源设置已修改，请刷新后重试。")
        before = {key: getattr(source, key) for key in fields}
        for key, value in fields.items():
            setattr(source, key, value)
        threshold_changed = "selection_threshold" in fields and before["selection_threshold"] != source.selection_threshold
        mode_changed = "participation_mode" in fields and before["participation_mode"] != source.participation_mode
        reproject_source(session, source, threshold_changed=threshold_changed, mode_changed=mode_changed)
        audit(session, "source.update", f"source:{source.id}", reason=why,
              changes={"before": before, "after": fields})
        result = source_view(source)
        session.commit()
        return result

    @router.get("/admin/sources/{source_id}/runs", dependencies=protected)
    def source_runs(source_id: UUID, session: Session = Depends(session_dep)):
        required(session, Source, str(source_id))
        runs = session.scalars(select(SourceRun).where(SourceRun.source_id == str(source_id))
                               .order_by(SourceRun.started_at.desc()).limit(50))
        return {"rows": [{"id": row.id, "status": row.status, "error": row.error_code,
                          "started_at": row.started_at, "finished_at": row.finished_at,
                          "candidate_count": row.candidate_count, "metrics": row.fetch_metrics} for row in runs]}

    @router.get("/admin/content", dependencies=protected)
    def content_list(q: str = Query("", max_length=200), page: int = Query(1, ge=1, le=100_000),
                     session: Session = Depends(session_dep)):
        query = select(Material)
        if q.strip():
            query = query.where(or_(Material.id == q.strip(),
                                    Material.source_title.contains(q.strip(), autoescape=True),
                                    Material.zh_title.contains(q.strip(), autoescape=True)))
        return {"page": page, "rows": [content_view(item) for item in session.scalars(
            query.order_by(Material.first_seen_at.desc(), Material.id).limit(50).offset((page - 1) * 50))]}

    @router.get("/admin/content/{item_id}", dependencies=protected)
    def content_detail(item_id: UUID, session: Session = Depends(session_dep)):
        item = required(session, Material, str(item_id))
        member = session.get(FactReport, item.id)
        fact = session.get(FactGroup, member.fact_id) if member else None
        override = session.get(AdminContentOverride, item.id)
        receipts = session.scalars(select(PaidReceipt).where(
            PaidReceipt.subject.startswith(f"article:{item.id}:", autoescape=True))
                                   .order_by(PaidReceipt.updated_at.desc()).limit(30))
        return {**content_view(item), "editorial": item.editorial_data, "standalone": item.standalone,
                "fact_id": member.fact_id if member else None, "story_id": fact.story_id if fact else None,
                "override": override.fields if override else {},
                "receipts": [{"key": row.key, "purpose": row.purpose, "status": row.status,
                              "attempts": row.latest_attempt} for row in receipts]}

    @router.post("/admin/content/{item_id}/visibility", dependencies=protected)
    def visibility(item_id: UUID, body: Visibility, session: Session = Depends(session_dep)):
        why = reason(body)
        begin_write(session)
        item = required(session, Material, str(item_id))
        before = item.withdrawn
        item.withdrawn = body.withdrawn
        if item.relevant is not None:
            project_visibility(item)
        if before and item.public and item.featured_candidate and item.selected_at is None:
            admin_rerun(session, item, "group", explicit=False)
        audit(session, "content.visibility", f"material:{item.id}", reason=why,
              changes={"before": before, "after": item.withdrawn})
        result = content_view(item)
        session.commit()
        return result

    @router.post("/admin/content/{item_id}/override", dependencies=protected)
    def override_content(item_id: UUID, body: ContentOverride, session: Session = Depends(session_dep)):
        why = reason(body)
        fields = body.model_dump(exclude_unset=True, exclude={"reason"})
        if not fields or any(isinstance(value, str) and not value.strip() for value in fields.values()):
            raise error(400, "invalid_request", "请填写有效的人工覆盖字段。")
        topics = fields.get("topics")
        if topics is not None and (set(topics) - set(PUBLIC_TOPIC_SLUGS) or len(set(topics)) != len(topics)):
            raise error(400, "invalid_request", "分类不在八类目录内或重复。")
        begin_write(session)
        item = required(session, Material, str(item_id))
        existing = session.get(AdminContentOverride, item.id)
        previous = dict(existing.fields) if existing else {}
        effective = dict(previous)
        for key, value in fields.items():
            if value is None:
                effective.pop(key, None)
            else:
                effective[key] = value.strip() if isinstance(value, str) else value
        if fields.get("selected") is True and (item.editorial_revision != item.revision or
                                              len((item.editorial_data or {}).get("scores", [])) != 2):
            raise error(409, "scores_required", "当前修订需要完成两次独立评分。")
        if existing is None:
            existing = AdminContentOverride(material_id=item.id)
            session.add(existing)
        existing.fields, existing.updated_at = effective, now_utc()
        base = (item.editorial_data or {}).get("model_fields", {})
        can_project = item.relevant is not None
        if can_project and any(key in previous and value is None and key != "selected" and key not in base
                               for key, value in fields.items()):
            # An older analysis lacks the unoverridden values. Rebuild from its receipts.
            item.public, can_project = False, False
            admin_rerun(session, item, "analyze", explicit=False)
        if can_project:
            for key in (fields.keys() & OVERRIDE_FIELDS) - {"selected"}:
                if key in effective or key in base:
                    setattr(item, key, effective.get(key, base.get(key)))
            if "relevant" in fields and "relevant" not in effective and not automatic_relevance_allowed(item):
                item.relevant = False
            if "topics" in fields:
                session.execute(delete(MaterialTopic).where(MaterialTopic.material_id == item.id))
                session.add_all(MaterialTopic(material_id=item.id, topic_slug=topic) for topic in item.topics)
            project_visibility(item)
            newly_candidate = refresh_candidate(item, effective) if fields.keys() & {"selected", "relevant"} else False
            if newly_candidate or fields.get("selected") is True:
                admin_rerun(session, item, "group", explicit=False)
        audit(session, "content.override", f"material:{item.id}", reason=why,
              changes={"fields": sorted(fields)})
        session.commit()
        return {"override": effective}

    @router.post("/admin/content/{item_id}/rerun", status_code=202, dependencies=protected)
    def rerun(item_id: UUID, body: Rerun, session: Session = Depends(session_dep)):
        why = reason(body)
        begin_write(session)
        item = required(session, Material, str(item_id))
        active = session.scalar(select(WorkItem.id).where(WorkItem.kind == body.step,
            WorkItem.status.in_(("pending", "running")), WorkItem.payload["material_id"].as_string() == item.id).limit(1))
        if active:
            raise error(409, "conflict", "已有同类任务排队或执行中。")
        row = admin_rerun(session, item, body.step, explicit=True)
        identifier = row.id
        audit(session, "content.rerun", f"material:{item.id}", reason=why, changes={"step": body.step, "job": identifier})
        session.commit()
        return {"job_id": identifier}

    @router.post("/admin/content/{item_id}/membership", dependencies=protected)
    def membership(item_id: UUID, body: Membership, session: Session = Depends(session_dep)):
        from .grouping import correct_membership

        why = reason(body)
        if body.fact_id and body.standalone:
            raise error(400, "invalid_request", "请在归入事实和保持独立之间选择一项。")
        begin_write(session)
        required(session, Material, str(item_id))
        target = str(body.fact_id) if body.fact_id else None
        try:
            changed = correct_membership(session, str(item_id), fact_id=target, standalone=body.standalone)
        except ValueError as exc:
            raise error(409, "conflict", "归组目标无效或已变更。") from exc
        if not changed:
            raise error(409, "conflict", "归组目标无效或已变更。")
        audit(session, "content.membership", f"material:{item_id}", reason=why,
              changes={"fact_id": target, "standalone": body.standalone})
        session.commit()
        return {"updated": True}

    @router.post("/admin/stories/merge", dependencies=protected)
    def merge(body: Merge, session: Session = Depends(session_dep)):
        from .grouping import merge_stories

        why = reason(body)
        begin_write(session)
        try:
            changed = body.from_id != body.into_id and merge_stories(session, str(body.from_id), str(body.into_id))
        except ValueError as exc:
            raise error(409, "conflict", "事件无法合并。") from exc
        if not changed:
            raise error(409, "conflict", "事件无法合并。")
        audit(session, "story.merge", f"story:{body.from_id}", reason=why, changes={"into": str(body.into_id)})
        session.commit()
        return {"updated": True}

    @router.get("/admin/runs", dependencies=protected)
    def runs(session: Session = Depends(session_dep)):
        counts = session.execute(select(WorkItem.kind, WorkItem.status, func.count()).group_by(
            WorkItem.kind, WorkItem.status).order_by(WorkItem.kind, WorkItem.status))
        due_count = session.scalar(select(func.count()).select_from(WorkItem).where(
            WorkItem.status == "pending", WorkItem.due_at <= now_utc()))
        unknown_count = session.scalar(select(func.count()).select_from(PaidReceipt).where(PaidReceipt.status == "unknown"))
        jobs = session.scalars(select(WorkItem).order_by(WorkItem.due_at.desc()).limit(80))
        attempts = session.execute(select(PaidReceipt, PaidAttempt).join(
            PaidAttempt, (PaidAttempt.receipt_key == PaidReceipt.key) & (PaidAttempt.number == PaidReceipt.latest_attempt)
        ).order_by((PaidReceipt.status == "unknown").desc(), PaidReceipt.updated_at.desc()).limit(80))
        return {"queue": [{"kind": kind, "status": status, "count": count} for kind, status, count in counts],
                "pending_due": due_count, "unknown_receipts": unknown_count,
                "jobs": [{"id": row.id, "kind": row.kind, "status": row.status, "attempts": row.attempts,
                          "error": row.error, "due_at": row.due_at,
                          **({"failed_editions": (row.result or {}).get("failed", []),
                              "pending_editions": (row.result or {}).get("pending", []),
                              "generated_editions": (row.result or {}).get("generated", []),
                              "updated_editions": (row.result or {}).get("updated", [])} if row.kind == "daily" else {})}
                         for row in jobs],
                "receipts": [{"key": row.key, "subject": row.subject, "purpose": row.purpose, "status": row.status,
                              "attempts": row.latest_attempt, "updated_at": row.updated_at, "error": attempt.error,
                              "service": attempt.service, "billed": attempt.billed, "release_note": attempt.release_note}
                             for row, attempt in attempts]}

    @router.post("/admin/runs/{job_id}/requeue", dependencies=protected)
    def retry(job_id: UUID, body: AdminReason, session: Session = Depends(session_dep)):
        why = reason(body)
        begin_write(session)
        required(session, WorkItem, str(job_id))
        if not requeue(session, str(job_id)):
            raise error(409, "conflict", "只能恢复失败或待运行任务。")
        audit(session, "work.requeue", f"work:{job_id}", reason=why)
        session.commit()
        return {"queued": True}

    @router.post("/admin/receipts/{key}/release", dependencies=protected)
    def release(key: str, body: ReceiptRelease, session: Session = Depends(session_dep)):
        from .receipts import release_unknown

        why = reason(body)
        begin_write(session)
        required(session, PaidReceipt, key)
        if not release_unknown(session, key, billed=body.billed, note=why):
            raise error(409, "conflict", "回执已处置或不在未知状态。")
        audit(session, "receipt.release", f"receipt:{key}", reason=why, changes={"billed": body.billed})
        session.commit()
        return {"released": True}

    @router.get("/admin/models", dependencies=protected)
    def models(session: Session = Depends(session_dep)):
        aliases = available_presets()
        settings = {row.capability: row.model for row in session.scalars(select(AdminModelSetting))}
        return {"aliases": aliases, "rows": [{"capability": key, "label": label, "override": settings.get(key)}
                                             for key, label in CAPABILITIES.items()]}

    @router.post("/admin/models/{capability}", dependencies=protected)
    def choose_model(capability: str, body: ModelChoice, session: Session = Depends(session_dep)):
        why = reason(body)
        if capability not in CAPABILITIES or body.model is not None and body.model not in available_presets():
            raise error(400, "invalid_request", "能力或模型别名未配置。")
        begin_write(session)
        row = session.get(AdminModelSetting, capability)
        old = row.model if row else None
        if body.model is None and row:
            session.delete(row)
        elif body.model is not None:
            if row is None:
                row = AdminModelSetting(capability=capability)
                session.add(row)
            row.model, row.updated_at = body.model, now_utc()
        audit(session, "model.switch", f"capability:{capability}", reason=why,
              changes={"before": old, "after": body.model})
        session.commit()
        return {"capability": capability, "override": body.model}

    @router.get("/admin/evaluations", dependencies=protected)
    def evaluations(session: Session = Depends(session_dep)):
        rows = session.scalars(select(AdminEvaluation).order_by(AdminEvaluation.id.desc()).limit(100))
        return {"rows": [{"id": row.id, "label": row.label, "created_at": row.created_at,
                          "models": list(row.report.get("models", {}))} for row in rows]}

    @router.get("/admin/evaluations/{identifier}", dependencies=protected)
    def evaluation(identifier: int, session: Session = Depends(session_dep)):
        row = required(session, AdminEvaluation, identifier)
        return {"id": row.id, "label": row.label, "report": row.report}

    @router.post("/admin/evaluations", status_code=201, dependencies=protected)
    def import_evaluation(body: EvaluationImport, session: Session = Depends(session_dep)):
        report = body.report
        models = report.get("models")
        if (not body.label.strip() or not isinstance(models, dict) or not models or
                any(not isinstance(model, dict) or not isinstance(model.get("summary"), dict)
                    for model in models.values()) or len(json.dumps(report, ensure_ascii=False)) > 1_000_000):
            raise error(400, "invalid_request", "评测需要包含模型摘要的 SelectBench 报告。")
        begin_write(session)
        row = AdminEvaluation(label=body.label.strip(), report=report)
        session.add(row)
        session.flush()
        identifier = row.id
        audit(session, "evaluation.import", f"evaluation:{identifier}", changes={"models": list(models)})
        session.commit()
        return {"id": identifier}

    @router.get("/admin/daily", dependencies=protected)
    def daily_list(session: Session = Depends(session_dep)):
        from .edition_models import DailyIssue

        rows = session.scalars(select(DailyIssue).order_by(DailyIssue.key.desc()).limit(80))
        return {"rows": [{"key": row.key, "version": row.version, "generated_at": row.generated_at} for row in rows]}

    @router.post("/admin/daily/{key}/correct", dependencies=protected)
    def daily_correct(key: date, body: DailyCorrection, session: Session = Depends(session_dep)):
        from .daily_reports import compose_daily
        from .edition_models import DailyIssue

        why = reason(body)
        day = key.isoformat()
        begin_write(session)
        previous = required(session, DailyIssue, day)
        if previous.version != body.version:
            raise error(409, "conflict", "刊期已修改，请刷新后重试。")
        try:
            issue = compose_daily(session, day, reason=why, actor=ACTOR,
                                  expected_version=body.version, commit=False)
        except ValueError as exc:
            raise error(409, "daily_unavailable", "刊期无法订正，检查分析和归组状态。") from exc
        version = issue["version"]
        if issue["written"]:
            audit(session, "daily.correct", f"daily:{day}", reason=why,
                  changes={"before": body.version, "after": version})
        session.commit()
        return {"key": day, "version": version}
