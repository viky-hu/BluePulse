from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(20))
    country_code: Mapped[str | None] = mapped_column(String(8))
    language: Mapped[str] = mapped_column(String(20), default="zh")
    source_type: Mapped[str] = mapped_column(String(30), default="official")
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_hosts: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    excerpt_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    full_text_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    min_body_status: Mapped[str] = mapped_column(String(20), default="full_text", server_default="full_text")
    selection_threshold: Mapped[int | None] = mapped_column(Integer)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name_zh: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("topics.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="running")
    error_code: Mapped[str | None] = mapped_column(String(60))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    fetch_metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    source: Mapped[Source] = relationship()
    source_title: Mapped[str] = mapped_column(Text)
    title_key: Mapped[str | None] = mapped_column(String(64), index=True)
    source_body: Mapped[str | None] = mapped_column(Text)
    body_source_url: Mapped[str | None] = mapped_column(Text)
    source_summary: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(20))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_date: Mapped[date | None] = mapped_column(Date)
    published_sort_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), default="analysis_pending")
    timeline_kind: Mapped[str] = mapped_column(String(20), default="unknown")
    body_status: Mapped[str] = mapped_column(String(20), default="metadata_only")
    translation_status: Mapped[str] = mapped_column(String(24), default="not_required")
    zh_title: Mapped[str | None] = mapped_column(Text)
    zh_summary: Mapped[str | None] = mapped_column(Text)
    zh_body: Mapped[str | None] = mapped_column(Text)
    importance_score: Mapped[int] = mapped_column(Integer, default=0)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    relevant: Mapped[bool | None] = mapped_column(Boolean)
    featured_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    selection_status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    grouping_status: Mapped[str] = mapped_column(String(20), default="pending")
    duplicate_of_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"), index=True)
    duplicate_reason: Mapped[str | None] = mapped_column(String(60))
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    withdrawn: Mapped[bool] = mapped_column(Boolean, default=False)
    published_public_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str | None] = mapped_column(String(200))


class MaterialRevision(Base):
    __tablename__ = "material_revisions"
    __table_args__ = (UniqueConstraint("material_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    source_title: Mapped[str] = mapped_column(Text)
    source_body: Mapped[str | None] = mapped_column(Text)
    body_source_url: Mapped[str | None] = mapped_column(Text)
    source_summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_date: Mapped[date | None] = mapped_column(Date)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MaterialTopic(Base):
    __tablename__ = "material_topics"
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), primary_key=True)
    topic_slug: Mapped[str] = mapped_column(String(100), primary_key=True)


class Discovery(Base):
    __tablename__ = "discoveries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("source_runs.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"))
    url: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(30))
    reason_code: Mapped[str | None] = mapped_column(String(60))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AnalysisAttempt(Base):
    __tablename__ = "analysis_attempts"
    __table_args__ = (UniqueConstraint("material_id", "revision", "input_version", "attempt"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    input_version: Mapped[str] = mapped_column(String(50))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    result: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FeaturedEdition(Base):
    __tablename__ = "featured_editions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    window_policy: Mapped[str] = mapped_column(String(40), default="24h_then_7d")
    slots: Mapped[list[FeaturedSlot]] = relationship(back_populates="edition", order_by="FeaturedSlot.slot")


class FeaturedSlot(Base):
    __tablename__ = "featured_slots"
    __table_args__ = (UniqueConstraint("edition_id", "slot"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    edition_id: Mapped[str] = mapped_column(ForeignKey("featured_editions.id"))
    article_id: Mapped[str] = mapped_column(ForeignKey("materials.id"))
    slot: Mapped[str] = mapped_column(String(3))
    importance_score: Mapped[int] = mapped_column(Integer)
    featured_reason: Mapped[str | None] = mapped_column(Text)
    edition: Mapped[FeaturedEdition] = relationship(back_populates="slots")
    article: Mapped[Material] = relationship()


Index("ix_materials_public_date", Material.public, Material.published_at)
