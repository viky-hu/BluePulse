"""Public v1 response contract consumed by the existing Next.js frontend."""
from __future__ import annotations

from typing import Generic, TypeVar

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


class TimelineCardOut(Contract):
    key: str
    anchorAt: str
    item: TimelineArticleOut
    group: None = None


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
