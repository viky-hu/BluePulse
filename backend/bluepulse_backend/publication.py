from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FeaturedEdition, FeaturedSlot, Material, now_utc


MIN_BODY_CHARS = 300


def evidence_allowed(material: Material) -> bool:
    """A substantial captured body is the minimum for automatic public eligibility."""
    return bool(material.body_status == "full_text" and
                len("".join((material.source_body or "").split())) >= MIN_BODY_CHARS)


def visible(material: Material) -> bool:
    return bool(material.public and material.duplicate_of_id is None and
                not material.withdrawn and material.relevant and
                material.source.excerpt_allowed and evidence_allowed(material))


def refresh_source_publication(session: Session, source_id: str) -> dict[str, int]:
    """Apply current source permission to completed model results without another paid call."""
    changed = {"released": 0, "hidden": 0}
    rows = session.scalars(select(Material).where(
        Material.source_id == source_id,
        Material.state.in_(["publication_pool", "publication_hidden"]),
    )).all()
    for material in rows:
        eligible = bool(material.relevant and material.duplicate_of_id is None and
                        material.source.excerpt_allowed and evidence_allowed(material) and
                        (material.zh_summary or "").strip() and not material.withdrawn)
        if material.public == eligible:
            continue
        material.public = eligible
        material.state = "publication_pool" if eligible else "publication_hidden"
        if eligible:
            material.published_public_at = material.published_public_at or now_utc()
            changed["released"] += 1
        else:
            changed["hidden"] += 1
    session.commit()
    return changed


def create_featured_edition(session: Session, article_ids: list[str]) -> FeaturedEdition:
    """Explicit selection boundary. An upstream grouper must complete before inclusion."""
    if len(article_ids) > 6 or len(article_ids) != len(set(article_ids)):
        raise ValueError("invalid_featured_selection")
    articles = session.scalars(select(Material).where(Material.id.in_(article_ids))).all()
    by_id = {article.id: article for article in articles}
    if any(article_id not in by_id or not visible(by_id[article_id]) or
           not by_id[article_id].featured_candidate or
           by_id[article_id].grouping_status != "complete" or
           by_id[article_id].timeline_kind != "fresh" for article_id in article_ids):
        raise ValueError("article_not_featured_eligible")
    edition = FeaturedEdition()
    session.add(edition)
    session.flush()
    for index, article_id in enumerate(article_ids):
        article = by_id[article_id]
        session.add(FeaturedSlot(
            edition_id=edition.id, article_id=article_id, slot=f"p{index}",
            importance_score=article.importance_score,
        ))
    session.commit()
    return edition
