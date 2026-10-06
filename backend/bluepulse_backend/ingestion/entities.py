from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from bluepulse_backend.models import Article, ArticleEntity, Entity


def _alias_matches(text: str, alias: str) -> bool:
    # Latin names require word boundaries; Chinese aliases are exact substrings.
    if re.search(r"[A-Za-z0-9]", alias):
        return re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", text, re.I) is not None
    return alias in text


def match_entities(article: Article, catalog: Iterable[Entity]) -> list[tuple[Entity, str, str]]:
    fields = (
        ("source_title", article.source_title),
        ("zh_title", article.zh_title),
        ("zh_summary", article.zh_summary),
        ("source_body", article.source_body),
    )
    matches: list[tuple[Entity, str, str]] = []
    for entity in catalog:
        if not entity.enabled:
            continue
        aliases = sorted(set(entity.aliases or [entity.name]), key=len, reverse=True)
        for field, text in fields:
            alias = next((candidate for candidate in aliases if candidate and text and
                          _alias_matches(text, candidate)), None)
            if alias:
                matches.append((entity, field, alias))
                break
    return matches


def link_article_entities(session: Session, article: Article, catalog: Iterable[Entity]) -> int:
    session.execute(delete(ArticleEntity).where(ArticleEntity.article_id == article.id))
    if article.processing_status != "processed":
        return 0
    matches = match_entities(article, catalog)
    for entity, field, alias in matches:
        session.add(ArticleEntity(
            article_id=article.id, entity_id=entity.id,
            evidence_field=field, matched_alias=alias,
        ))
    return len(matches)
