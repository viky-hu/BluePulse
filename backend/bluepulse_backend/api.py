from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db import make_engine, make_session_factory
from .models import FeaturedEdition, Material, MaterialTopic, Source, Topic
from .publication import visible
from .schemas import (
    ArticleCardOut, ArticleDetailOut, ArticleListOut, AvailabilityOut, EntityListOut,
    FeaturedOut, HealthOut, ItemsOut, SourceOut, TimelineOut, TopicOut,
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value.tzinfo is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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


def create_app(database: str | None = None) -> FastAPI:
    engine = make_engine(database)
    session_factory = make_session_factory(engine)
    app = FastAPI(title="Blue Pulse API", version="0.2.0")
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
            if visible(slot.article) and slot.article.featured_candidate and slot.article.grouping_status == "complete":
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
        """Recent public materials only; grouping, selection and hot remain unavailable."""
        filters = {"region": region, "topic": topic}
        key = _filter_hash(["site-timeline", region, topic])
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
        if cursor:
            boundary_at, article_id, _ = _read_cursor(cursor, "recent", key)
            query = query.where(or_(effective < boundary_at,
                                    and_(effective == boundary_at, Material.id > article_id)))
        rows = session.scalars(query.order_by(effective.desc(), Material.id).limit(limit + 1)).all()
        more = len(rows) > limit
        rows = rows[:limit]
        day_counts: dict[str, int] = {}
        shanghai = timezone(timedelta(hours=8))  # Current publication dates; no Windows tzdata dependency.
        cards = []
        for row in rows:
            anchor = row.published_sort_at or row.published_at
            if anchor is None:
                continue
            aware = anchor if anchor.tzinfo else anchor.replace(tzinfo=UTC)
            day = aware.astimezone(shanghai).date().isoformat()
            day_counts[day] = day_counts.get(day, 0) + 1
            cards.append({"key": row.id, "anchorAt": iso(anchor), "item": {**_card(row), "selected": False},
                          "group": None})
        return {"filters": filters, "cards": cards,
                "nextCursor": _cursor_for(rows[-1], "recent", key) if more else None,
                "hot": None, "dayCounts": day_counts}

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
