from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now_utc, uid


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (UniqueConstraint("kind", "identity"), Index("ix_work_due", "status", "due_at"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(24))
    identity: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    token: Mapped[str | None] = mapped_column(String(36))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict | None] = mapped_column(JSON)


class PaidReceipt(Base):
    __tablename__ = "paid_receipts"
    __table_args__ = (Index("ix_receipt_subject_step", "subject", "purpose", "status"),)

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(String(40))
    request: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latest_attempt: Mapped[int] = mapped_column(Integer, default=0)
    auto_released: Mapped[bool] = mapped_column(Boolean, default=False)


class PaidAttempt(Base):
    __tablename__ = "paid_attempts"
    __table_args__ = (Index("ix_paid_attempts_budget", "service", "sent_at"),)

    receipt_key: Mapped[str] = mapped_column(ForeignKey("paid_receipts.key"), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(100))
    run_key: Mapped[str | None] = mapped_column(String(120), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24))
    response: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(100))
    release_note: Mapped[str | None] = mapped_column(Text)
    billed: Mapped[bool | None] = mapped_column(Boolean)


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("stories.id"))


class StorySignal(Base):
    __tablename__ = "story_signals"

    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), primary_key=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), primary_key=True, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    participant_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="editorial")


class StoryDigest(Base):
    __tablename__ = "story_digests"

    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    digest: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FactMention(Base):
    __tablename__ = "fact_mentions"

    fact_id: Mapped[str] = mapped_column(ForeignKey("fact_groups.id"), primary_key=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), primary_key=True, index=True)
    revision: Mapped[int] = mapped_column(Integer)


class EmbeddingVector(Base):
    __tablename__ = "embedding_vectors"

    config_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    text_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    vector: Mapped[list[float]] = mapped_column(JSON)
