from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AdminAccount(Base):
    __tablename__ = "admin_accounts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(1000))
    adapter: Mapped[str] = mapped_column(String(32))
    region: Mapped[str | None] = mapped_column(String(16), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    language: Mapped[str] = mapped_column(String(12), default="en")
    source_type: Mapped[str] = mapped_column(String(32), default="media")
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    trust_level: Mapped[int] = mapped_column(Integer, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    articles: Mapped[list[Article]] = relationship(back_populates="source")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name_zh: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(2000))
    canonical_url: Mapped[str] = mapped_column(String(2000), unique=True)
    source_title: Mapped[str] = mapped_column(Text)
    zh_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    zh_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    zh_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(12), default="en")
    region: Mapped[str | None] = mapped_column(String(16), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    importance_score: Mapped[int] = mapped_column(Integer, default=0)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="pending_model")
    parse_status: Mapped[str] = mapped_column(String(32), default="metadata_only")
    quality_status: Mapped[str] = mapped_column(String(32), default="unreviewed")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[Source] = relationship(back_populates="articles")
    topics: Mapped[list[Topic]] = relationship(secondary="article_topics")
    media: Mapped[list[ArticleMedia]] = relationship(back_populates="article")


class ArticleTopic(Base):
    __tablename__ = "article_topics"

    article_id: Mapped[UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class ArticleMedia(Base):
    __tablename__ = "article_media"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    article_id: Mapped[UUID] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    url: Mapped[str] = mapped_column(String(2000))
    thumbnail_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="linked")

    article: Mapped[Article] = relationship(back_populates="media")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    trigger_type: Mapped[str] = mapped_column(String(24), default="manual")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="running")
    counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"))
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    status: Mapped[str] = mapped_column(String(24), default="running")
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeaturedEdition(Base):
    __tablename__ = "featured_editions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    window_policy: Mapped[str] = mapped_column(String(32), default="24h_then_7d")
    slots: Mapped[list[FeaturedSlot]] = relationship(back_populates="edition")


class FeaturedSlot(Base):
    __tablename__ = "featured_slots"
    __table_args__ = (
        UniqueConstraint("edition_id", "slot"),
        UniqueConstraint("edition_id", "article_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    edition_id: Mapped[UUID] = mapped_column(ForeignKey("featured_editions.id", ondelete="CASCADE"))
    article_id: Mapped[UUID] = mapped_column(ForeignKey("articles.id"))
    slot: Mapped[str] = mapped_column(String(2))
    importance_score: Mapped[int] = mapped_column(Integer, default=0)

    edition: Mapped[FeaturedEdition] = relationship(back_populates="slots")
    article: Mapped[Article] = relationship()
