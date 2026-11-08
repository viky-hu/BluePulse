from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HotRanking(Base):
    __tablename__ = "hot_rankings"

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    rule_version: Mapped[str] = mapped_column(String(48))
    entries: Mapped[list[dict]] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON)


class StoryHeatHour(Base):
    __tablename__ = "story_heat_hourly"

    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), primary_key=True)
    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, index=True)
    heat: Mapped[float] = mapped_column(Float)
    participants: Mapped[int] = mapped_column(Integer)
    cohort: Mapped[int] = mapped_column(Integer)
    complete: Mapped[bool] = mapped_column(Boolean)
    evidence_hash: Mapped[str] = mapped_column(String(64))


class DailyIssue(Base):
    __tablename__ = "daily_issues"

    key: Mapped[str] = mapped_column(String(10), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content: Mapped[dict] = mapped_column(JSON)


class DailyIssueRevision(Base):
    __tablename__ = "daily_issue_revisions"

    issue_key: Mapped[str] = mapped_column(ForeignKey("daily_issues.key"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSON)
