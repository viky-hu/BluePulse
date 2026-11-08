"""Current public classification metadata, independent of source/model internals."""
from __future__ import annotations

import hashlib
import unicodedata

from sqlalchemy import case, func, select

from .models import Material, Source
from .publication import visible
from .public_reads import listed_query


ENTITY_TYPES = {"vendor", "model", "organization"}


def _canonical(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def entity_slug(name: str, kind: str) -> str:
    return f"{kind}-{hashlib.sha256(_canonical(name).encode()).hexdigest()[:24]}"


def _metadata(article):
    if article.source.full_text_allowed and article.editorial_revision == article.revision:
        if isinstance(article.editorial_data, dict):
            return article.editorial_data
    return {}


def entity_links(article) -> list[dict]:
    links = {}
    for entity in _metadata(article).get("entities") or ():
        if not isinstance(entity, dict):
            continue
        name, kind = entity.get("name"), entity.get("type")
        if isinstance(name, str) and name.strip() and isinstance(kind, str) and kind in ENTITY_TYPES:
            slug = entity_slug(name, kind)
            if entity.get("slug") == slug:
                links.setdefault(slug, {"slug": slug, "name": name, "entity_type": kind})
    return list(links.values())


def public_tags(article) -> list[str]:
    return list(dict.fromkeys(
        tag for tag in (_metadata(article).get("tags") or ())
        if isinstance(tag, str) and tag.strip() and not tag.startswith("entity:")
    ))


def with_metadata_match(query, *, tag=None, entity=None):
    """An exact match on the current revision's approved metadata, before pagination."""
    if tag or entity:
        query = query.where(Source.full_text_allowed.is_(True), Material.editorial_revision == Material.revision)
    if tag:
        tags = func.json_each(Material.editorial_data, "$.tags").table_valued("value")
        query = query.where(select(1).select_from(tags).where(tags.c.value == tag).correlate(Material).exists())
    if entity:
        entities = func.json_each(Material.editorial_data, "$.entities").table_valued("value", "type")
        entity_value = case((entities.c.type == "object", entities.c.value), else_="{}")
        query = query.where(select(1).select_from(entities).where(
            func.json_extract(entity_value, "$.slug") == entity,
        ).correlate(Material).exists())
    return query


def entity_page(session, *, kind=None, region=None, q=None, cursor=None, limit=20):
    query = listed_query().where(Source.full_text_allowed.is_(True), Material.editorial_revision == Material.revision)
    if region:
        query = query.where(Source.region == region)
    search = _canonical(q) if q else ""
    found = {}
    for article in session.scalars(query.order_by(Material.id).execution_options(yield_per=100)):
        if not visible(article):
            continue
        for link in entity_links(article):
            slug = link["slug"]
            if (cursor and slug <= cursor or kind and link["entity_type"] != kind or
                    search and search not in _canonical(link["name"])):
                continue
            current = found.setdefault(slug, {**link, "article_count": 0, "region": article.source.region})
            current["article_count"] += 1
            if current["region"] != article.source.region:
                current["region"] = None
            current["name"] = min(current["name"], link["name"])
    rows = [found[slug] for slug in sorted(found)[:limit]]
    return {"items": rows, "next_cursor": rows[-1]["slug"] if len(found) > limit else None, "limit": limit}
