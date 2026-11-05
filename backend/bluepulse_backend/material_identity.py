"""Conservative same-copy detection and publication-date precision rules."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Material


def title_key(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    plain = "".join(char for char in normalized if char.isalnum())
    return hashlib.sha256(plain.encode()).hexdigest() if len(plain) >= 12 else ""


def publication_clock(published_at: datetime | None, published_date: date | None,
                      seen: datetime) -> tuple[str, datetime | None, datetime | None]:
    """Return timeline, sortable time and trustworthy exact time; never invent exact time."""
    if seen.tzinfo is None:
        raise ValueError("seen_without_timezone")
    if published_at is not None:
        if published_at.tzinfo is None:
            raise ValueError("published_at_without_timezone")
        exact = published_at.astimezone(UTC)
        if exact > seen + timedelta(hours=1):
            return "unknown", None, None
        return ("historical" if seen - exact > timedelta(hours=48) else "fresh", exact, exact)
    if published_date is None or published_date > seen.date():
        return "unknown", None, None
    # Midnight is only an internal sort key. published_at remains null for date-only pages.
    sort_at = datetime.combine(published_date, time.min, tzinfo=UTC)
    # A date-only page cannot prove it was published within the last 24 hours.
    timeline = "fresh" if published_date >= seen.date() - timedelta(days=1) else "historical"
    return timeline, sort_at, None


def _published_day(material: Material) -> date | None:
    if material.published_date is not None:
        return material.published_date
    if material.published_at is not None:
        exact = material.published_at
        return (exact if exact.tzinfo else exact.replace(tzinfo=UTC)).astimezone(UTC).date()
    return None


def _shingles(body: str | None) -> set[str]:
    normalized = re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", body or "").casefold())
    if len(normalized) < 400:
        return set()
    return {normalized[index:index + 24] for index in range(len(normalized) - 23)}


def same_copy(left: Material, right: Material) -> bool:
    """Only exact-title, same-day, strongly overlapping full bodies are auto linked."""
    if (left.id == right.id or not left.title_key or
            left.title_key != right.title_key or _published_day(left) is None or
            _published_day(left) != _published_day(right)):
        return False
    a, b = _shingles(left.source_body), _shingles(right.source_body)
    return bool(a and b and len(a & b) / min(len(a), len(b)) >= 0.8)


def reconcile_title(session: Session, key: str | None) -> None:
    """Recompute links after insert/revision; keep each source record and provenance."""
    if not key:
        return
    rows = session.scalars(select(Material).where(Material.title_key == key)).all()
    def seen_utc(row: Material) -> datetime:
        value = row.first_seen_at
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)

    rows.sort(key=lambda row: (not row.source.excerpt_allowed,
                               row.source.source_type != "official",
                               seen_utc(row), row.id))
    roots: list[Material] = []
    for row in rows:
        was_duplicate = row.duplicate_of_id is not None
        row.duplicate_of_id = None
        row.duplicate_reason = None
        root = next((item for item in roots if same_copy(item, row)), None)
        if root is None:
            roots.append(row)
            if was_duplicate and row.state == "duplicate_hidden":
                row.state = "analysis_pending"  # Reapply the saved result under the current link policy.
        else:
            row.duplicate_of_id = root.id
            row.duplicate_reason = "same_title_day_body_overlap"
            row.public = False
            row.state = "duplicate_hidden"  # Do not spend a model call on the mirrored copy.
    session.flush()
