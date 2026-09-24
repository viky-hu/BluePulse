from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from bluepulse_backend.db import create_database_engine
from bluepulse_backend.models import Article, FeaturedEdition, FeaturedSlot, Source, Topic

router = APIRouter(prefix="/api/v1")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


@lru_cache(maxsize=1)
def _get_engine():
    return create_database_engine()


def get_session():
    engine = _get_engine()
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def _error(code: str, message: str, request_id: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )


def _filter_key(
    period: str,
    topic: str | None,
    region: str | None,
    source: UUID | None,
    source_type: str | None,
    q: str | None,
) -> str:
    payload = json.dumps(
        [period, topic, region, str(source) if source else None, source_type, q],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")


def _encode_cursor(sort: str, filter_key: str, article: Article) -> str:
    effective = article.published_at or article.first_seen_at
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=UTC)
    else:
        effective = effective.astimezone(UTC)
    payload: dict[str, object] = {
        "sort": sort,
        "filters": filter_key,
        "published_at": _iso_utc(effective),
        "id": str(article.id),
    }
    if sort == "importance":
        payload["importance_score"] = article.importance_score
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, sort: str, filter_key: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if payload.get("sort") != sort or payload.get("filters") != filter_key:
            raise ValueError
        payload["published_at"] = datetime.fromisoformat(payload["published_at"])
        payload["id"] = UUID(payload["id"])
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ApiError(400, "invalid_cursor", "游标无效，或与当前筛选条件不匹配。") from None


def _source_out(source: Source) -> dict[str, object]:
    return {
        "id": str(source.id),
        "name": source.name,
        "slug": source.slug,
        "region": source.region,
        "country_code": source.country_code,
        "language": source.language,
        "source_type": source.source_type,
        "topics": source.topics,
    }


def _card_out(article: Article) -> dict[str, object]:
    return {
        "id": str(article.id),
        "title": article.zh_title or article.source_title,
        "source_title": article.source_title,
        "published_at": _iso_utc(article.published_at),
        "language": article.language,
        "region": article.region,
        "country_code": article.country_code,
        "url": article.source_url,
        "source": _source_out(article.source),
        "importance_score": article.importance_score,
        "processing_status": article.processing_status,
        "parse_status": article.parse_status,
    }


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/sources")
def list_sources(session: SessionDep) -> dict[str, object]:
    sources = session.scalars(
        select(Source).where(Source.enabled.is_(True)).order_by(Source.name.asc())
    )
    return {"items": [_source_out(source) for source in sources]}


@router.get("/taxonomy")
def list_taxonomy(session: SessionDep) -> dict[str, object]:
    topics = session.scalars(
        select(Topic).where(Topic.enabled.is_(True)).order_by(Topic.slug.asc())
    )
    return {
        "items": [
            {
                "id": str(topic.id),
                "slug": topic.slug,
                "name_zh": topic.name_zh,
                "name_en": topic.name_en,
                "parent_id": str(topic.parent_id) if topic.parent_id else None,
            }
            for topic in topics
        ]
    }


@router.get("/home/featured")
def featured(session: SessionDep) -> dict[str, object]:
    edition = session.scalar(
        select(FeaturedEdition).order_by(FeaturedEdition.generated_at.desc()).limit(1)
    )
    if edition is None:
        return {"generated_at": None, "window_policy": "24h_then_7d", "items": []}
    rows = session.execute(
        select(FeaturedSlot, Article)
        .join(Article, FeaturedSlot.article_id == Article.id)
        .where(FeaturedSlot.edition_id == edition.id, Article.deleted_at.is_(None))
        .options(joinedload(Article.source))
        .order_by(FeaturedSlot.slot.asc())
    ).all()
    return {
        "generated_at": edition.generated_at.isoformat(),
        "window_policy": edition.window_policy,
        "items": [
            {
                "slot": slot.slot,
                "article": _card_out(article),
                "importance_score": slot.importance_score,
            }
            for slot, article in rows
        ],
    }


@router.get("/articles")
def list_articles(
    session: SessionDep,
    period: str = Query("30d", pattern="^(24h|7d|30d)$"),
    topic: str | None = None,
    region: str | None = Query(None, pattern="^(domestic|foreign)$"),
    source: UUID | None = None,
    source_type: str | None = None,
    q: str | None = Query(None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("recent", pattern="^(recent|importance)$"),
) -> dict[str, object]:
    now = datetime.now(UTC)
    period_start = now - {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }[period]
    effective_date = func.coalesce(Article.published_at, Article.first_seen_at)
    query = (
        select(Article)
        .join(Source)
        .options(joinedload(Article.source), selectinload(Article.topics))
        .where(Article.deleted_at.is_(None), effective_date >= period_start)
    )
    if topic:
        query = query.where(Article.topics.any(Topic.slug == topic))
    if region:
        query = query.where(Article.region == region)
    if source:
        query = query.where(Article.source_id == source)
    if source_type:
        query = query.where(Source.source_type == source_type)
    if q:
        escaped = q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
        query = query.where(
            or_(
                func.lower(Article.source_title).like(term, escape="\\"),
                func.lower(Article.zh_title).like(term, escape="\\"),
                func.lower(Article.source_body).like(term, escape="\\"),
                func.lower(Article.zh_summary).like(term, escape="\\"),
            )
        )

    filter_key = _filter_key(period, topic, region, source, source_type, q)
    if cursor:
        decoded = _decode_cursor(cursor, sort, filter_key)
        cursor_date = decoded["published_at"]
        cursor_id = decoded["id"]
        date_boundary = or_(
            effective_date < cursor_date,
            and_(effective_date == cursor_date, Article.id > cursor_id),
        )
        if sort == "importance":
            score = decoded.get("importance_score", 0)
            query = query.where(
                or_(
                    Article.importance_score < score,
                    and_(Article.importance_score == score, date_boundary),
                )
            )
            query = query.order_by(Article.importance_score.desc(), effective_date.desc(), Article.id.asc())
        else:
            query = query.where(date_boundary).order_by(effective_date.desc(), Article.id.asc())
    elif sort == "importance":
        query = query.order_by(Article.importance_score.desc(), effective_date.desc(), Article.id.asc())
    else:
        query = query.order_by(effective_date.desc(), Article.id.asc())

    rows = list(session.scalars(query.limit(limit + 1)).unique())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = _encode_cursor(sort, filter_key, items[-1]) if has_more and items else None
    return {
        "items": [
            {
                **_card_out(article),
                "topics": [topic.slug for topic in article.topics],
                "summary": article.zh_summary,
            }
            for article in items
        ],
        "next_cursor": next_cursor,
        "limit": limit,
    }


@router.get("/articles/{article_id}")
def article_detail(article_id: UUID, session: SessionDep) -> dict[str, object]:
    article = session.scalar(
        select(Article)
        .where(Article.id == article_id, Article.deleted_at.is_(None))
        .options(
            joinedload(Article.source),
            selectinload(Article.topics),
            selectinload(Article.media),
        )
    )
    if article is None:
        raise ApiError(404, "article_not_found", "文章不存在。")
    return {
        **_card_out(article),
        "source_body": article.source_body,
        "zh_body": article.zh_body,
        "summary": article.zh_summary,
        "author": article.author,
        "first_seen_at": _iso_utc(article.first_seen_at),
        "fetched_at": _iso_utc(article.fetched_at),
        "quality_status": article.quality_status,
        "topics": [topic.slug for topic in article.topics],
        "media": [
            {
                "kind": media.kind,
                "url": media.url,
                "thumbnail_url": media.thumbnail_url,
                "caption": media.caption,
                "alt_text": media.alt_text,
                "position": media.position,
                "status": media.status,
            }
            for media in article.media
        ],
        "comments": {"available": False, "count": 0, "items": []},
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Blue Pulse API", version="1.0.0")
    origins = [
        origin.strip()
        for origin in os.environ.get(
            "BLUEPULSE_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return _error(exc.code, exc.message, request.state.request_id, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _error("invalid_request", "请求参数无效。", request.state.request_id, 422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError):
        return _error("database_unavailable", "数据服务暂不可用。", request.state.request_id, 503)

    app.include_router(router)
    return app


app = create_app()
