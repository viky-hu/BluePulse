"""Public v1 response contract consumed by the existing Next.js frontend."""
from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceOut(Contract):
    id: str
    name: str
    slug: str
    region: str | None
    country_code: str | None
    language: str
    source_type: str
    topics: list[str]


class TopicOut(Contract):
    id: str
    slug: str
    name_zh: str
    name_en: str
    parent_id: str | None


class EntityLink(Contract):
    slug: str
    name: str
    entity_type: str


class EntityOut(EntityLink):
    region: str | None
    article_count: int


class MediaPreview(Contract):
    kind: str
    url: str
    thumbnail_url: str | None
    alt_text: str | None
    caption: str | None = None


class ArticleCardOut(Contract):
    id: str
    title: str
    source_title: str
    published_at: str | None
    published_date: str | None = None
    timeline_kind: str
    first_seen_at: str | None
    language: str
    region: str | None
    country_code: str | None
    url: str
    source: SourceOut
    importance_score: int = Field(ge=0, le=100)
    processing_status: str
    parse_status: str
    body_status: str
    translation_status: str
    topics: list[str]
    summary: str | None
    media_preview: MediaPreview | None
    entities: list[EntityLink]


class MediaOut(MediaPreview):
    position: int | None = None
    status: str | None = None


class CommentsOut(Contract):
    available: bool
    count: int
    items: list[dict]


class ArticleDetailOut(ArticleCardOut):
    source_body: str | None
    body_source_url: str | None
    zh_body: str | None
    author: str | None
    fetched_at: str | None
    quality_status: str
    media: list[MediaOut]
    comments: CommentsOut


class TimelineArticleOut(ArticleCardOut):
    selected: bool = False


class GroupInfoOut(Contract):
    factId: str
    additionalSourceCount: int
    reportCount: int


class TimelineCardOut(Contract):
    key: str
    anchorAt: str
    item: TimelineArticleOut
    group: GroupInfoOut | None = None


class GroupReportOut(Contract):
    id: str
    title: str
    source: dict[str, str]
    timelineAt: str
    originalUrl: str


class GroupReportsOut(Contract):
    factId: str
    reports: list[GroupReportOut]


class TimelineOut(Contract):
    filters: dict[str, str]
    cards: list[TimelineCardOut]
    nextCursor: str | None
    hot: None = None
    dayCounts: dict[str, int]


class FeaturedItemOut(Contract):
    slot: str
    article: ArticleCardOut
    importance_score: int
    featured_reason: str | None


class FeaturedOut(Contract):
    generated_at: str | None
    window_policy: str
    items: list[FeaturedItemOut]


class ArticleListOut(Contract):
    items: list[ArticleCardOut]
    next_cursor: str | None
    limit: int


class EntityListOut(Contract):
    items: list[EntityOut]
    next_cursor: str | None
    limit: int


class AvailabilityItem(Contract):
    id: str
    available: bool


class AvailabilityOut(Contract):
    items: list[AvailabilityItem]


T = TypeVar("T")


class ItemsOut(Contract, Generic[T]):
    items: list[T]


class HealthOut(Contract):
    status: str


class AutoPublicationRequest(Contract):
    idempotency_key: str = Field(min_length=1, max_length=100)
    source_slugs: list[str] | None = None
    max_items: int = Field(default=2, ge=1, le=2)
    max_model_calls: int = Field(default=0, ge=0, le=50)


class AutoPublicationJobOut(Contract):
    id: str
    status: str
    source_slugs: list[str]
    max_items: int
    max_model_calls: int
    created_at: str
    started_at: str | None
    finished_at: str | None
    error_code: str | None
    report: dict | None


class AgentSourceOut(Contract):
    name: str
    slug: str


class AgentItemOut(Contract):
    id: str
    title: str
    summary: str
    source: AgentSourceOut
    published_at: str | None
    published_date: str | None
    date_precision: Literal["datetime", "date", "unknown"]
    first_seen_at: str
    site_url: str
    original_url: str


class AgentQueryOut(Contract):
    kind: Literal["latest", "search"]
    window: Literal["24h", "7d", "30d", "all"]
    limit: int
    q: str | None
    sort_basis: Literal["source_publication_then_first_seen"]


class AgentListOut(Contract):
    schema_version: int
    query: AgentQueryOut
    items: list[AgentItemOut]
