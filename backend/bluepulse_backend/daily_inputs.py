"""Publication windows and collection evidence for the Pulse daily edition."""
from bisect import bisect_left
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from .edition_evidence import public_at, utc
from .models import FactGroup, FactReport, Material, Source, SourceRun


BEIJING = timezone(timedelta(hours=8))
DAY = timedelta(days=1)
RECOVERY_WINDOW = 7 * DAY
COLLECTION_GAP = timedelta(hours=2)
FIRST_IMPORT_FRESHNESS = timedelta(hours=48)
SUCCESS = ("completed", "no_candidates")


def daily_window(key: str) -> tuple[datetime, datetime]:
    day = date.fromisoformat(key)
    if day.isoformat() != key:
        raise ValueError("invalid_daily_date")
    end = datetime.combine(day, time(8), BEIJING).astimezone(UTC)
    return end - DAY, end


def edition_key(at):
    local = utc(at).astimezone(BEIJING)
    return (local.date() + (DAY if local.hour >= 8 else timedelta())).isoformat()


def daily_inputs(session, start, end, now, *, historical_source_dates=False):
    first_run = session.scalar(select(func.min(SourceRun.started_at)))
    first_key = edition_key(first_run) if first_run else None
    sources = set(session.scalars(select(Source.id).where(
        Source.enabled.is_(True), Source.participation_mode == "editorial")))
    runs = defaultdict(list)
    for source_id, finished, metrics in session.execute(select(
            SourceRun.source_id, SourceRun.finished_at, SourceRun.fetch_metrics).where(
            SourceRun.status.in_(SUCCESS), SourceRun.finished_at >= start - RECOVERY_WINDOW,
            SourceRun.finished_at < end).order_by(SourceRun.finished_at)):
        metrics = metrics or {}
        if metrics.get("mode") in {"bounded", "historical"} or (
                "collection_rule_version" in metrics and metrics.get("coverage") != "complete"):
            continue
        runs[source_id].append(utc(finished))

    def succeeded(source_id, lower, upper):
        times = runs[source_id]
        index = bisect_left(times, lower)
        return index < len(times) and times[index] < upper

    query = (select(Material, FactGroup).join(Material.source).options(joinedload(Material.source))
             .outerjoin(FactReport, and_(FactReport.material_id == Material.id,
                                        FactReport.revision == Material.revision,
                                        FactReport.relation.in_(("primary", "report"))))
             .outerjoin(FactGroup, FactGroup.id == FactReport.fact_id)
             .where(Source.participation_mode == "editorial", Material.withdrawn.is_(False),
                    Material.duplicate_of_id.is_(None), Material.first_seen_at <= now)
             .order_by(Material.id))
    if historical_source_dates:
        # Date-only originals belong to the following morning's issue; never invent an hour.
        source_day = start.astimezone(BEIJING).date()
        query = query.where(or_(
            and_(Material.published_at >= start, Material.published_at < end),
            and_(Material.published_at.is_(None), Material.published_date == source_day,
                 Material.timeline_kind != "unknown"),
        ))
    else:
        query = query.where(Material.first_seen_at >= start, Material.first_seen_at < end + RECOVERY_WINDOW)
    ready, details = [], []
    window_key = edition_key(start)
    waiting = 0
    for item, fact in session.execute(query):
        seen = utc(item.first_seen_at)
        exact = utc(item.published_at) if item.published_at else None
        day = item.published_date if not exact and item.timeline_kind != "unknown" else None
        # For date-only evidence only a fetch after the calendar day is known to have occurred after publication.
        date_end = datetime.combine(day + DAY, time.min, BEIJING) if day else None
        published_key = edition_key(exact) if exact else (day + DAY).isoformat() if day else None
        key = edition_key(seen)
        reason = "first_seen"
        if historical_source_dates:
            key, reason = published_key, "historical_source_date"
        elif item.backfill_reason == "collection-audit" and published_key and published_key < key:
            key, reason = published_key, "recovered_collection_audit"
        elif published_key and published_key < key and (first_key is None or published_key >= first_key):
            _, original_end = daily_window(published_key)
            after_publication = exact or date_end
            if (seen - original_end <= RECOVERY_WINDOW
                    and not succeeded(item.source_id, min(original_end - COLLECTION_GAP, after_publication), original_end)):
                key, reason = published_key, "recovered_collection_gap"

        historical = item.timeline_kind in {"historical", "backfill"} or item.backfill_reason == "stale-on-discovery"
        if key != window_key or (historical and reason == "first_seen" and
                                 (not published_key or seen - (exact or date_end) > RECOVERY_WINDOW)):
            continue
        if not historical_source_dates and item.backfill_reason == "first-import" and (
            not published_key or (seen - (exact or date_end)) > FIRST_IMPORT_FRESHNESS
        ):
            continue
        judged = (item.editorial_revision == item.revision and item.collection_state != "pending"
                  and (item.judged_at is None or utc(item.judged_at) <= now))
        available = judged and public_at(item, now)
        pending = (not judged or item.public and not available
                   or available and item.grouping_status == "pending")
        waiting += pending
        if available:
            ready.append((item, fact if item.grouping_status == "complete" and item.editorial_scope != "composite" else None))
        details.append({"itemId": item.id, "source": item.source.slug, "title": item.zh_title or item.source_title,
                        "firstSeenAt": seen.isoformat(), "sourceDate": exact.isoformat() if exact else day.isoformat() if day else None,
                        "assignment": reason, "available": available, "pending": pending})
    covered = sum(succeeded(source_id, end - COLLECTION_GAP, end) for source_id in sources)
    return ready, details, {"sourcesExpected": len(sources), "sourcesCovered": covered, "pendingReports": waiting}
