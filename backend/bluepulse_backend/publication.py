from __future__ import annotations

from datetime import UTC
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .admin_models import AdminContentOverride
from .models import FeaturedEdition, FeaturedSlot, Material, now_utc


MIN_BODY_CHARS = 300


def evidence_allowed(material: Material) -> bool:
    """A substantial captured body is the minimum for automatic public eligibility."""
    return bool(material.body_status == "full_text" and
                len("".join((material.source_body or "").split())) >= MIN_BODY_CHARS)


def source_link_allowed(material: Material) -> bool:
    try:
        parts = urlsplit(material.source_url)
        _ = parts.port
        return bool(parts.scheme in {"http", "https"} and parts.hostname and
                    not parts.username and not parts.password and
                    not any(char.isspace() for char in parts.netloc))
    except ValueError:
        return False


def visible(material: Material, *, at=None) -> bool:
    return bool(material.public and _eligible(material) and (
        material.visible_after is None or _utc(material.visible_after) <= _utc(at or now_utc())))


def _utc(value):
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def automatic_relevance_allowed(material: Material) -> bool:
    data = material.editorial_data or {}
    decision = data.get("prefilter")
    if decision is None:
        # Pre-upgrade PASS stays public while awaiting recheck. Older classifiers used a boolean.
        return data.get("label") in (None, "PASS")
    return bool(material.editorial_revision == material.revision and data.get("label") == "PASS" and
                decision.get("label") == "PASS" and decision.get("relevance") in ("direct", "potential") and
                decision.get("evidence") and decision.get("reason"))


def relevance_allowed(material: Material) -> bool:
    if not material.relevant:
        return False
    if automatic_relevance_allowed(material):
        return True
    session = object_session(material)
    override = session.get(AdminContentOverride, material.id) if session is not None else None
    return bool(override and override.fields.get("relevant") is True)


def _eligible(material: Material) -> bool:
    return bool(material.duplicate_of_id is None and
                not material.withdrawn and relevance_allowed(material) and
                (not (material.editorial_data or {}).get("prefilter") or material.topics) and
                material.source.participation_mode == "editorial" and
                material.source.excerpt_allowed and evidence_allowed(material) and
                (material.zh_summary or "").strip() and source_link_allowed(material))


def selected(material: Material, *, at=None) -> bool:
    return bool(visible(material, at=at) and material.selected_at and
                _utc(material.selected_at) <= _utc(at or now_utc()) and material.featured_candidate and
                material.grouping_status == "complete" and material.grouping_value is not False and
                material.editorial_revision == material.revision and material.timeline_kind == "fresh")


def translation_needed(material: Material, *, at=None, replace_current: bool = False) -> bool:
    return bool(material.source.full_text_allowed and material.collection_state != "pending" and
                material.editorial_revision == material.revision and
                not material.language.lower().startswith("zh") and
                (replace_current or material.translation_revision != material.revision) and visible(material, at=at))


def project_visibility(material: Material, now=None) -> bool:
    material.public = _eligible(material)
    material.state = "publication_pool" if material.public else "publication_hidden"
    if material.public and not material.published_public_at:
        material.published_public_at = now or now_utc()
    return material.public


def refresh_source_publication(session: Session, source_id: str) -> dict[str, int]:
    """Apply current source permission to completed model results without another paid call."""
    changed = {"released": 0, "hidden": 0}
    rows = session.scalars(select(Material).where(
        Material.source_id == source_id,
        Material.state.in_(["publication_pool", "publication_hidden"]),
    )).all()
    for material in rows:
        eligible = _eligible(material)
        if material.public == eligible:
            continue
        project_visibility(material)
        if eligible:
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
