"""Read-side policy for confirmed human decisions over model suggestions."""

from __future__ import annotations

from sqlalchemy import and_, or_

from bluepulse_backend.models import Article


def public_article_conditions():
    return (
        Article.deleted_at.is_(None),
        Article.processing_status == "processed",
        Article.parse_status != "metadata_only",
        or_(Article.editorial_relevance.is_(None),
            Article.editorial_relevance.in_(("direct", "potential"))),
        or_(Article.editorial_select.is_(None), Article.editorial_select != "uncertain"),
    )


def featured_article_condition():
    return or_(
        Article.editorial_select == "select",
        and_(Article.editorial_select.is_(None), Article.featured_candidate.is_(True)),
    )


def featured_reason(article: Article) -> str | None:
    if article.editorial_select == "select":
        return article.editorial_reason
    return article.featured_reason
