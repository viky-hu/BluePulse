"""The current Article–Fact–Story evidence used by the two public editions."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from .editorial_models import Story, StorySignal
from .models import FactGroup, FactReport, Material
from .publication import visible


def utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def public_at(material: Material, at: datetime) -> bool:
    return visible(material, at=at) and (
        material.published_public_at is None or utc(material.published_public_at) <= at
    )


def title_of(material: Material) -> str:
    return material.zh_title or material.source_title


def timeline_at(material: Material) -> datetime:
    return utc(material.published_at or material.published_sort_at or material.first_seen_at)


def story_reports(session: Session, story_id: str, at: datetime) -> list[tuple[Material, FactGroup]]:
    rows = session.execute(
        select(Material, FactGroup).options(joinedload(Material.source))
        .join(FactReport, and_(FactReport.material_id == Material.id, FactReport.revision == Material.revision))
        .join(FactGroup, FactGroup.id == FactReport.fact_id)
        .join(Story, Story.id == FactGroup.story_id)
        .where(Story.id == story_id, Story.merged_into_id.is_(None),
               FactReport.relation.in_(("primary", "report")), Material.grouping_status == "complete",
               Material.standalone.is_(False))
    )
    return [(material, fact) for material, fact in rows if material.editorial_scope != "composite"
            and material.source.participation_mode == "editorial" and public_at(material, at)]


@dataclass(frozen=True, slots=True)
class Signal:
    story_id: str
    article_id: str
    fact_id: str | None
    revision: int
    participant: str
    source_id: str
    name: str
    tier: str | None
    kind: str
    at: datetime


def _participant_key(source) -> str:
    if source.participant_key:
        return "group:" + " ".join(source.participant_key.split()).casefold()
    if source.owner_entity:
        return "owner:" + " ".join(source.owner_entity.split()).casefold()
    return "source:" + source.id


def current_signals(
    session: Session, start: datetime, end: datetime, *, visible_at: datetime,
    story_ids: set[str] | None = None,
) -> list[Signal]:
    statement = (
        select(StorySignal, Material, FactGroup)
        .join(Story, Story.id == StorySignal.story_id)
        .join(Material, and_(Material.id == StorySignal.material_id, Material.revision == StorySignal.revision))
        .outerjoin(FactReport, and_(FactReport.material_id == Material.id, FactReport.revision == Material.revision,
                                   FactReport.relation.in_(("primary", "report"))))
        .outerjoin(FactGroup, and_(FactGroup.id == FactReport.fact_id, FactGroup.story_id == StorySignal.story_id))
        .options(joinedload(Material.source))
        .where(Story.merged_into_id.is_(None), StorySignal.observed_at >= start, StorySignal.observed_at <= end,
               Material.published_at.is_not(None), Material.withdrawn.is_(False), Material.duplicate_of_id.is_(None),
               Material.timeline_kind == "fresh", Material.grouping_status == "complete",
               Material.standalone.is_(False))
    )
    if story_ids is not None:
        statement = statement.where(StorySignal.story_id.in_(story_ids))
    result = []
    for signal, article, fact in session.execute(statement):
        source = article.source
        mode = source.participation_mode
        if mode == "isolated" or article.editorial_scope == "composite":
            continue
        if mode == "editorial" and (fact is None or not public_at(article, visible_at)):
            continue
        result.append(Signal(
            signal.story_id, article.id, fact.id if fact else None, article.revision,
            _participant_key(source), source.id, source.name, source.tier,
            "editorial" if mode == "editorial" else "signal", utc(signal.observed_at),
        ))
    return result
