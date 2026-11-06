from __future__ import annotations

import base64
import hashlib
import json
import hmac
import os
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import make_engine, make_session_factory
from .models import AutoPublicationJob, FactGroup, FactReport, FeaturedEdition, FeaturedSlot, Material, MaterialTopic, Source, Topic
from .auto_publication import enqueue_job
from .fact_grouping import AUTO_WINDOW
from .publication import visible
from .schemas import (
    ArticleCardOut, ArticleDetailOut, ArticleListOut, AvailabilityOut, EntityListOut,
    AutoPublicationJobOut, AutoPublicationRequest, FeaturedOut, GroupReportsOut,
    HealthOut, ItemsOut, SourceOut, TimelineOut, TopicOut,
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value.tzinfo is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_seconds(value: datetime) -> float:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).timestamp()


def _error(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "request_id": request_id,
    }}, headers={"X-Request-ID": request_id, "Cache-Control": "no-store"})


def _source(source: Source) -> dict:
    return {"id": source.id, "name": source.name, "slug": source.slug,
            "region": source.region, "country_code": source.country_code,
            "language": source.language, "source_type": source.source_type,
            "topics": source.topics}


def _card(article: Material) -> dict:
    return {
        "id": article.id, "title": article.zh_title or article.source_title,
        "source_title": article.source_title, "published_at": iso(article.published_at),
        "published_date": article.published_date.isoformat() if article.published_date else None,
        "timeline_kind": article.timeline_kind,
        "first_seen_at": iso(article.first_seen_at), "language": article.language,
        "region": article.source.region, "country_code": article.source.country_code,
        "url": article.source_url, "source": _source(article.source),
        "importance_score": article.importance_score,
        "processing_status": "completed" if article.state == "publication_pool" else article.state,
        "parse_status": article.body_status, "body_status": article.body_status,
        "translation_status": article.translation_status,
        "topics": article.topics, "summary": article.zh_summary,
        "media_preview": None, "entities": [],
    }


def _detail(article: Material) -> dict:
    return {
        **_card(article),
        "source_body": article.source_body if article.source.full_text_allowed else None,
        "body_source_url": article.body_source_url,
        "zh_body": article.zh_body if article.source.full_text_allowed else None,
        "author": article.author, "fetched_at": iso(article.fetched_at),
        "quality_status": "model_processed" if article.state == "publication_pool" else article.state,
        "media": [], "comments": {"available": False, "count": 0, "items": []},
    }


def _job(row: AutoPublicationJob) -> dict:
    return {"id": row.id, "status": row.status, "source_slugs": row.source_slugs,
            "max_items": row.max_items, "max_model_calls": row.max_model_calls,
            "created_at": iso(row.created_at), "started_at": iso(row.started_at),
            "finished_at": iso(row.finished_at), "error_code": row.error_code,
            "report": row.report}


def _filter_hash(filters: list[object]) -> str:
    return hashlib.sha256(json.dumps(filters, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:16]


def _cursor_for(article: Material, sort: str, key: str) -> str:
    data = {"v": 1, "sort": sort, "filter": key,
            "date": iso(article.published_sort_at or article.published_at or article.first_seen_at),
            "id": article.id, "score": article.importance_score}
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def _read_cursor(value: str, sort: str, key: str) -> tuple[datetime, str, int]:
    try:
        data = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        if data["v"] != 1 or data["sort"] != sort or data["filter"] != key:
            raise ValueError
        date = datetime.fromisoformat(data["date"].replace("Z", "+00:00"))
        article_id = str(UUID(data["id"]))
        score = int(data["score"])
        if not 0 <= score <= 100:
            raise ValueError
        return date, article_id, score
    except (KeyError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ApiError(400, "invalid_cursor", "游标无效，或与当前筛选条件不匹配。") from None


def _timeline_cursor(anchor: datetime, group_id: str, key: str) -> str:
    value = {"v": 1, "sort": "timeline_group", "filter": key,
             "date": iso(anchor), "id": group_id, "score": 0}
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def create_app(database: str | None = None) -> FastAPI:
    engine = make_engine(database)
    session_factory = make_session_factory(engine)
    app = FastAPI(title="Blue Pulse API", version="0.3.0")
    router = APIRouter(prefix="/api/v1")

    def session_dep():
        with session_factory() as session:
            yield session

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID")
        request_id = supplied if supplied and len(supplied) <= 128 else str(uuid4())
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except SQLAlchemyError:
            response = _error(503, "database_unavailable", "数据服务暂时不可用。", request_id)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return _error(exc.status, exc.code, exc.message, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return _error(422, "invalid_request", "请求参数无效。", request.state.request_id)

    @router.get("/health/live", response_model=HealthOut)
    def live():
        return {"status": "ok"}

    @router.get("/health/ready", response_model=HealthOut)
    def ready(session: Session = Depends(session_dep)):
        session.execute(text("SELECT 1"))
        session.execute(select(Source.id).limit(1))
        return {"status": "ready"}

    def internal_token(x_bluepulse_worker_token: str | None = Header(None)) -> None:
        configured = os.environ.get("BLUEPULSE_INTERNAL_TOKEN", "")
        if not configured:
            raise ApiError(503, "internal_trigger_disabled", "自动出稿触发接口尚未启用。")
        if not x_bluepulse_worker_token or not hmac.compare_digest(x_bluepulse_worker_token, configured):
            raise ApiError(403, "forbidden", "无权操作自动出稿任务。")

    @router.post("/internal/auto-publication/jobs", response_model=AutoPublicationJobOut,
                 status_code=202, dependencies=[Depends(internal_token)])
    def create_auto_publication_job(body: AutoPublicationRequest,
                                    session: Session = Depends(session_dep)):
        try:
            job = enqueue_job(session, idempotency_key=body.idempotency_key,
                              source_slugs=body.source_slugs, max_items=body.max_items,
                              max_model_calls=body.max_model_calls)
        except ValueError as exc:
            raise ApiError(409 if str(exc) == "idempotency_key_reused" else 422,
                           str(exc), "自动出稿请求无效。") from None
        return _job(job)

    @router.get("/internal/auto-publication/jobs/{job_id}", response_model=AutoPublicationJobOut,
                dependencies=[Depends(internal_token)])
    def read_auto_publication_job(job_id: UUID, session: Session = Depends(session_dep)):
        job = session.get(AutoPublicationJob, str(job_id))
        if job is None:
            raise ApiError(404, "job_not_found", "任务不存在。")
        return _job(job)

    @router.get("/sources", response_model=ItemsOut[SourceOut])
    def sources(session: Session = Depends(session_dep)):
        rows = session.scalars(select(Source).where(Source.enabled.is_(True)).order_by(Source.name)).all()
        return {"items": [_source(row) for row in rows]}

    @router.get("/taxonomy", response_model=ItemsOut[TopicOut])
    def taxonomy(session: Session = Depends(session_dep)):
        rows = session.scalars(select(Topic).where(Topic.enabled.is_(True)).order_by(Topic.slug)).all()
        return {"items": [{"id": row.id, "slug": row.slug, "name_zh": row.name_zh,
                           "name_en": row.name_en, "parent_id": row.parent_id} for row in rows]}

    @router.get("/entities", response_model=EntityListOut)
    def entities(session: Session = Depends(session_dep), type: str | None = Query(None, pattern="^(vendor|model|organization)$"),
                 region: str | None = Query(None, pattern="^(domestic|foreign)$"),
                 q: str | None = Query(None, max_length=120), cursor: str | None = None,
                 limit: int = Query(20, ge=1, le=100)):
        # Entity extraction is outside the current M0-M2 backbone. Empty is factual.
        return {"items": [], "next_cursor": None, "limit": limit}

    @router.get("/home/featured", response_model=FeaturedOut)
    def featured(session: Session = Depends(session_dep)):
        edition = session.scalar(select(FeaturedEdition).order_by(FeaturedEdition.generated_at.desc(), FeaturedEdition.id.desc()).limit(1))
        if edition is None:
            return {"generated_at": None, "window_policy": "24h_then_7d", "items": []}
        items = []
        for slot in edition.slots:
            candidate_ok = (edition.window_policy == AUTO_WINDOW or slot.article.featured_candidate)
            recent_ok = (edition.window_policy != AUTO_WINDOW or
                         bool(slot.article.published_sort_at and
                              _utc_seconds(slot.article.published_sort_at) >=
                              (datetime.now(UTC) - timedelta(days=7)).timestamp()))
            if visible(slot.article) and candidate_ok and recent_ok and slot.article.grouping_status == "complete":
                items.append({"slot": slot.slot, "article": _card(slot.article),
                              "importance_score": slot.importance_score,
                              "featured_reason": slot.featured_reason})
        return {"generated_at": iso(edition.generated_at), "window_policy": edition.window_policy, "items": items}

    @router.get("/home/recently-collected", response_model=ItemsOut[ArticleCardOut])
    def recently_collected(session: Session = Depends(session_dep)):
        rows = session.scalars(select(Material).join(Source).where(
            Material.public.is_(True), Material.duplicate_of_id.is_(None),
            Material.withdrawn.is_(False), Material.relevant.is_(True),
            Source.excerpt_allowed.is_(True),
            or_(Material.body_status == "full_text",
                and_(Source.min_body_status == "abstract_only",
                     Material.body_status.in_(["abstract_only", "summary_only"]))),
        ).order_by(Material.first_seen_at.desc(), Material.id).limit(6)).all()
        return {"items": [_card(row) for row in rows]}

    @router.get("/site/timeline", response_model=TimelineOut)
    def site_timeline(
        session: Session = Depends(session_dep),
        region: str = Query("", pattern="^(|domestic|foreign)$"),
        topic: str = Query("", max_length=100),
        cursor: str | None = Query(None, max_length=2000),
        limit: int = Query(20, ge=1, le=40),
    ):
        """Recent public facts, grouped conservatively by exact title and source date."""
        filters = {"region": region, "topic": topic}
        key = _filter_hash(["site-timeline", region, topic])
        slots = session.scalars(select(FeaturedSlot).join(FeaturedEdition)).all()
        selected_ids = {slot.article_id for slot in slots if
                        slot.edition.window_policy == AUTO_WINDOW or slot.article.featured_candidate}
        if not selected_ids:
            return {"filters": filters, "cards": [], "nextCursor": None,
                    "hot": None, "dayCounts": {}}
        effective = func.coalesce(Material.published_sort_at, Material.published_at)
        query = select(Material).join(Source).where(
            Material.public.is_(True), Material.duplicate_of_id.is_(None),
            Material.withdrawn.is_(False), Material.relevant.is_(True),
            Source.excerpt_allowed.is_(True), Material.timeline_kind != "unknown",
            effective >= datetime.now(UTC) - timedelta(days=30),
            or_(Material.body_status == "full_text",
                and_(Source.min_body_status == "abstract_only",
                     Material.body_status.in_(["abstract_only", "summary_only"]))),
        )
        if region:
            query = query.where(Source.region == region)
        if topic:
            query = query.where(Material.id.in_(
                select(MaterialTopic.material_id).where(MaterialTopic.topic_slug == topic)))
        rows = [row for row in session.scalars(query.order_by(effective.desc(), Material.id)).all()
                if visible(row)]
        memberships = {item.material_id: item for item in session.scalars(select(FactReport).where(
            FactReport.material_id.in_([row.id for row in rows]))).all()} if rows else {}
        fact_ids = {item.fact_id for item in memberships.values()}
        facts = {item.id: item for item in session.scalars(select(FactGroup).where(
            FactGroup.id.in_(fact_ids))).all()} if fact_ids else {}
        grouped: dict[str, list[Material]] = {}
        for row in rows:
            member = memberships.get(row.id)
            group_id = member.fact_id if member and member.fact_id in facts else row.id
            grouped.setdefault(group_id, []).append(row)
        cards_data = []
        for group_id, members in grouped.items():
            selected_members = [item for item in members if item.id in selected_ids]
            if not selected_members:
                continue
            representative = min(selected_members, key=lambda item: (
                item.source.source_type != "official", not item.source.full_text_allowed,
                -_utc_seconds(item.published_sort_at or item.published_at or item.first_seen_at), item.id))
            anchor = (facts[group_id].anchor_at if group_id in facts else
                      representative.published_sort_at or representative.published_at or representative.first_seen_at)
            cards_data.append((anchor, group_id, representative, members))
        cards_data.sort(key=lambda item: (-_utc_seconds(item[0]), item[1]))
        all_cards_data = cards_data
        if cursor:
            boundary_at, group_id, _ = _read_cursor(cursor, "timeline_group", key)
            boundary = _utc_seconds(boundary_at)
            cards_data = [item for item in cards_data if
                          _utc_seconds(item[0]) < boundary or
                          (_utc_seconds(item[0]) == boundary and item[1] > group_id)]
        more = len(cards_data) > limit
        page = cards_data[:limit]
        day_counts: dict[str, int] = {}
        shanghai = timezone(timedelta(hours=8))  # Current publication dates; no Windows tzdata dependency.
        cards = []
        for anchor, _, _, _ in all_cards_data:
            aware = anchor if anchor.tzinfo else anchor.replace(tzinfo=UTC)
            day = aware.astimezone(shanghai).date().isoformat()
            day_counts[day] = day_counts.get(day, 0) + 1
        for anchor, group_id, row, members in page:
            additional = len({item.source_id for item in members if item.source_id != row.source_id})
            cards.append({"key": group_id, "anchorAt": iso(anchor),
                          "item": {**_card(row), "selected": row.id in selected_ids},
                          "group": ({"factId": group_id, "additionalSourceCount": additional,
                                     "reportCount": len(members)} if len(members) > 1 else None)})
        return {"filters": filters, "cards": cards,
                "nextCursor": _timeline_cursor(page[-1][0], page[-1][1], key) if more else None,
                "hot": None, "dayCounts": day_counts}

    @router.get("/site/groups/{fact_id}/reports", response_model=GroupReportsOut)
    def group_reports(fact_id: UUID, session: Session = Depends(session_dep),
                      region: str = Query("", pattern="^(|domestic|foreign)$"),
                      topic: str = Query("", max_length=100)):
        fact = session.get(FactGroup, str(fact_id))
        if fact is None:
            raise ApiError(404, "group_not_found", "阅读组不存在。")
        query = select(Material).join(FactReport, FactReport.material_id == Material.id).join(Source).where(
            FactReport.fact_id == fact.id, Material.public.is_(True),
            Material.duplicate_of_id.is_(None), Material.withdrawn.is_(False),
            Material.relevant.is_(True), Source.excerpt_allowed.is_(True))
        if region:
            query = query.where(Source.region == region)
        if topic:
            query = query.where(Material.id.in_(select(MaterialTopic.material_id).where(
                MaterialTopic.topic_slug == topic)))
        rows = [row for row in session.scalars(query.order_by(
            Material.published_sort_at.desc(), Material.id).limit(100)).all() if visible(row)]
        if not rows:
            raise ApiError(404, "group_not_found", "阅读组不存在。")
        return {"factId": fact.id, "reports": [{"id": row.id,
                "title": row.zh_title or row.source_title,
                "source": {"name": row.source.name},
                "timelineAt": iso(row.published_sort_at or row.published_at or row.first_seen_at),
                "originalUrl": row.source_url} for row in rows]}

    @router.get("/articles", response_model=ArticleListOut)
    def articles(
        session: Session = Depends(session_dep),
        period: str = Query("30d", pattern="^(24h|7d|30d|all)$"),
        topic: str | None = None,
        region: str | None = Query(None, pattern="^(domestic|foreign)$"),
        source: UUID | None = None,
        source_type: str | None = None,
        entity: str | None = Query(None, pattern="^[a-z0-9-]{1,100}$"),
        q: str | None = Query(None, max_length=200),
        cursor: str | None = Query(None, max_length=2000),
        limit: int = Query(20, ge=1, le=100),
        sort: str = Query("recent", pattern="^(recent|importance)$"),
    ):
        search = (q or "").strip()
        key = _filter_hash([period, topic, region, str(source) if source else None, source_type, entity, search])
        effective = func.coalesce(Material.published_sort_at, Material.published_at, Material.first_seen_at)
        query = select(Material).join(Source).where(
            Material.public.is_(True), Material.duplicate_of_id.is_(None),
            Material.withdrawn.is_(False), Material.relevant.is_(True),
            Source.excerpt_allowed.is_(True),
        )
        windows = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
        if period in windows:
            query = query.where(Material.timeline_kind != "unknown",
                                func.coalesce(Material.published_sort_at, Material.published_at)
                                >= datetime.now(UTC) - windows[period])
            if period == "24h":
                query = query.where(Material.published_at.is_not(None))
        if topic:
            query = query.where(Material.id.in_(
                select(MaterialTopic.material_id).where(MaterialTopic.topic_slug == topic)
            ))
        if region:
            query = query.where(Source.region == region)
        if source:
            query = query.where(Material.source_id == str(source))
        if source_type:
            query = query.where(Source.source_type == source_type)
        if entity:
            return {"items": [], "next_cursor": None, "limit": limit}
        if search:
            escaped = search.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            term = f"%{escaped}%"
            query = query.where(or_(
                func.lower(Material.source_title).like(term, escape="\\"),
                func.lower(Material.zh_title).like(term, escape="\\"),
                func.lower(Material.zh_summary).like(term, escape="\\"),
                func.lower(Material.source_body).like(term, escape="\\"),
            ))
        boundary = None
        if cursor:
            date, article_id, score = _read_cursor(cursor, sort, key)
            date_boundary = or_(effective < date, and_(effective == date, Material.id > article_id))
            boundary = (or_(Material.importance_score < score,
                            and_(Material.importance_score == score, date_boundary))
                        if sort == "importance" else date_boundary)
        if boundary is not None:
            query = query.where(boundary)
        if sort == "importance":
            query = query.order_by(Material.importance_score.desc(), effective.desc(), Material.id)
        else:
            query = query.order_by(effective.desc(), Material.id)
        query = query.where(or_(Material.body_status == "full_text",
                                and_(Source.min_body_status == "abstract_only",
                                     Material.body_status.in_(["abstract_only", "summary_only"]))))
        rows = session.scalars(query.limit(limit + 1)).all()
        more = len(rows) > limit
        rows = rows[:limit]
        return {"items": [_card(row) for row in rows],
                "next_cursor": _cursor_for(rows[-1], sort, key) if more else None,
                "limit": limit}

    @router.get("/articles/availability", response_model=AvailabilityOut)
    def availability(session: Session = Depends(session_dep), ids: str = ""):
        if not ids:
            return {"items": []}
        raw = ids.split(",")
        if len(raw) > 100:
            raise ApiError(422, "invalid_request", "请求参数无效。")
        try:
            article_ids = list(dict.fromkeys(str(UUID(item)) for item in raw))
        except ValueError:
            raise ApiError(422, "invalid_request", "请求参数无效。") from None
        rows = session.scalars(select(Material).where(Material.id.in_(article_ids))).all()
        available = {row.id for row in rows if visible(row)}
        return {"items": [{"id": item, "available": item in available} for item in article_ids]}

    @router.get("/articles/{article_id}", response_model=ArticleDetailOut)
    def detail(article_id: UUID, session: Session = Depends(session_dep)):
        article = session.get(Material, str(article_id))
        if article is None or not visible(article):
            raise ApiError(404, "article_not_found", "文章不存在。")
        return _detail(article)

    app.include_router(router)
    app.state.engine = engine
    app.state.session_factory = session_factory
    return app


app = create_app()
