"""Conservative fact identity and unscored recent featured editions."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import FactGroup, FactReport, FeaturedEdition, FeaturedSlot, Material, now_utc
from .publication import visible


AUTO_WINDOW = "auto_recent_7d"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _identity(material: Material) -> str:
    """Only an exact normalized title on the same source date may merge reports."""
    day = material.published_date
    if day is None and material.published_at is not None:
        day = _aware(material.published_at).date()
    if not material.title_key or day is None:
        value = f"single:{material.id}"
    else:
        value = f"title-day:{material.title_key}:{day.isoformat()}"
    return hashlib.sha256(value.encode()).hexdigest()


def group_public_materials(session: Session) -> dict[str, int]:
    rows = session.scalars(select(Material).options(joinedload(Material.source)).where(
        Material.public.is_(True), Material.duplicate_of_id.is_(None),
        Material.withdrawn.is_(False), Material.relevant.is_(True),
    ).order_by(Material.first_seen_at, Material.id)).all()
    created = assigned = revised = 0
    for material in rows:
        if not visible(material):
            continue
        key = _identity(material)
        fact = session.scalar(select(FactGroup).where(FactGroup.identity_key == key))
        if fact is None:
            fact = FactGroup(identity_key=key, title=material.zh_title or material.source_title,
                             anchor_at=material.published_sort_at or material.published_at or
                             material.first_seen_at)
            session.add(fact)
            session.flush()
            created += 1
        member = session.get(FactReport, material.id)
        if member is None:
            has_member = session.scalar(select(FactReport.material_id).where(
                FactReport.fact_id == fact.id).limit(1)) is not None
            member = FactReport(material_id=material.id, fact_id=fact.id,
                                revision=material.revision,
                                relation="report" if has_member else "primary")
            session.add(member)
            assigned += 1
        elif member.fact_id != fact.id or member.revision != material.revision:
            if member.fact_id != fact.id:
                has_member = session.scalar(select(FactReport.material_id).where(
                    FactReport.fact_id == fact.id).limit(1)) is not None
                member.relation = "report" if has_member else "primary"
            member.fact_id = fact.id
            member.revision = material.revision
            revised += 1
        material.grouping_status = "complete"
    session.commit()
    return {"groups_created": created, "members_assigned": assigned,
            "members_updated": revised}


def create_recent_featured(session: Session, *, now: datetime | None = None,
                           limit: int = 6) -> dict[str, object]:
    if not 1 <= limit <= 6:
        raise ValueError("invalid_featured_limit")
    moment = _aware(now or now_utc())
    candidates = session.scalars(select(Material).options(joinedload(Material.source)).where(
        Material.public.is_(True), Material.relevant.is_(True),
        Material.duplicate_of_id.is_(None), Material.withdrawn.is_(False),
        Material.grouping_status == "complete", Material.timeline_kind == "fresh",
        Material.published_sort_at >= moment - timedelta(days=7),
    ).order_by(Material.published_sort_at.desc(), Material.id)).all()
    eligible = [item for item in candidates if visible(item) and
                session.get(FactReport, item.id) is not None]
    picked: list[Material] = []
    used_facts: set[str] = set()
    used_sources: set[str] = set()
    for diversify in (True, False):
        for article in eligible:
            member = session.get(FactReport, article.id)
            if member.fact_id in used_facts or (diversify and article.source_id in used_sources):
                continue
            picked.append(article)
            used_facts.add(member.fact_id)
            used_sources.add(article.source_id)
            if len(picked) == limit:
                break
        if len(picked) == limit:
            break
    ids = [item.id for item in picked]
    latest = session.scalar(select(FeaturedEdition).order_by(
        FeaturedEdition.generated_at.desc(), FeaturedEdition.id.desc()).limit(1))
    if latest and latest.window_policy == AUTO_WINDOW and [slot.article_id for slot in latest.slots] == ids:
        return {"edition_id": latest.id, "created": False, "selected": len(ids)}
    edition = FeaturedEdition(window_policy=AUTO_WINDOW)
    session.add(edition)
    session.flush()
    for index, article in enumerate(picked):
        session.add(FeaturedSlot(edition_id=edition.id, article_id=article.id,
                                 slot=f"p{index}", importance_score=0,
                                 featured_reason="近期自动编排；未进行五轴评分"))
    session.commit()
    return {"edition_id": edition.id, "created": True, "selected": len(ids)}
