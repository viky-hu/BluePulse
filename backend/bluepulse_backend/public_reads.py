"""One current-public scope for browser and machine list queries."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models import Material, Source
from .publication import visible


WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7),
           "30d": timedelta(days=30)}


def listed_query():
    """SQL prefilter; visible() remains the final authority before pagination."""
    return select(Material).options(joinedload(Material.source)).join(Source).where(
        Material.public.is_(True), Material.duplicate_of_id.is_(None),
        Material.withdrawn.is_(False), Material.relevant.is_(True),
        Source.excerpt_allowed.is_(True), Material.body_status == "full_text",
    )


def within_publication_window(query, window: str, *, now: datetime | None = None):
    if window == "all":
        return query
    if window not in WINDOWS:
        raise ValueError("invalid_window")
    moment = now or datetime.now(UTC)
    published = func.coalesce(Material.published_sort_at, Material.published_at)
    query = query.where(Material.timeline_kind != "unknown",
                        published >= moment - WINDOWS[window])
    if window == "24h":
        # A date-only source page cannot prove publication within 24 hours.
        query = query.where(Material.published_at.is_not(None))
    return query


def with_public_text_match(query, search: str):
    """Search only title and published summary; private body text is not a match key."""
    term = search.strip().casefold()
    if not term:
        return query
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return query.where(or_(
        func.lower(Material.source_title).like(pattern, escape="\\"),
        func.lower(Material.zh_title).like(pattern, escape="\\"),
        func.lower(Material.zh_summary).like(pattern, escape="\\"),
    ))


def visible_page(session: Session, query, limit: int) -> tuple[list[Material], bool]:
    """Check current policy before counting a row toward a page."""
    rows: list[Material] = []
    for item in session.scalars(query.execution_options(yield_per=100)):
        if not visible(item):
            continue
        rows.append(item)
        if len(rows) > limit:
            break
    return rows[:limit], len(rows) > limit
