from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now_utc


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    binding: Mapped[str] = mapped_column(String(64))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AdminAudit(Base):
    __tablename__ = "admin_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(60), index=True)
    subject: Mapped[str | None] = mapped_column(String(120), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class AdminRateEvent(Base):
    __tablename__ = "admin_rate_events"
    __table_args__ = (Index("ix_admin_rate_events_scope_created", "scope", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AdminContentOverride(Base):
    __tablename__ = "admin_content_overrides"

    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), primary_key=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AdminModelSetting(Base):
    __tablename__ = "admin_model_settings"

    capability: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AdminEvaluation(Base):
    __tablename__ = "admin_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(160))
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(200))
    page_url: Mapped[str | None] = mapped_column(String(500))
    source_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FeedbackScreenshot(Base):
    __tablename__ = "feedback_screenshots"

    feedback_id: Mapped[int] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True)
    mime: Mapped[str] = mapped_column(String(16))
    data: Mapped[bytes] = mapped_column(LargeBinary)


class FeedbackBan(Base):
    __tablename__ = "feedback_bans"

    source_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
