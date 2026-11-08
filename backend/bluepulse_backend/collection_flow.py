"""AIHOT listing admission, extraction and source clocks on the Pulse queue."""
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json

from sqlalchemy import func, or_, select

from .editorial_models import WorkItem
from .models import Discovery, Material, Source
from .pipeline import Candidate, canonical_url, store_candidate
from .work_queue import enqueue, utc


FIRST_IMPORT_LIMIT = 30
FIRST_IMPORT_AGE = timedelta(days=12 * 30)
STALE_ON_DISCOVERY = timedelta(hours=48)
DETAIL_RETRY = timedelta(minutes=10)
DETAIL_MAX_ATTEMPTS = 3


def _pack(item):
    payload = asdict(item)
    for key in ("published_at", "published_date"):
        if payload[key] is not None:
            payload[key] = payload[key].isoformat()
    return payload


def unpack(payload):
    data = dict(payload)
    if data["published_at"]:
        data["published_at"] = datetime.fromisoformat(data["published_at"])
    if data["published_date"]:
        data["published_date"] = date.fromisoformat(data["published_date"])
    return Candidate(**data)


def _before(item, cutoff):
    if item.published_at:
        return utc(item.published_at) < utc(cutoff)
    return bool(item.published_date and item.published_date < cutoff.date())


def _lookup(session, url):
    return session.scalar(select(Material).where(Material.canonical_url == url))


def _merge(item, previous, *, listing):
    if not previous:
        return item
    verified = listing and bool(previous.source_body)
    exact = previous.published_at if verified and previous.published_at else item.published_at or previous.published_at
    return replace(
        item,
        title=previous.source_title if verified or not item.title.strip() else item.title,
        body=(previous.source_body if not item.body else item.body),
        summary=previous.source_summary if verified and previous.source_summary else item.summary or previous.source_summary,
        published_at=utc(exact) if exact else None,
        published_date=(previous.published_date if verified and previous.published_date else
                        item.published_date or previous.published_date),
        body_source_url=item.body_source_url or previous.body_source_url,
        media=item.media if item.media is not None else previous.source_media,
        author=item.author or previous.author,
    )


def admit_page(session, source, run, candidates, now, cursor):
    first = source.collection_initialized_at is None
    imported = set(cursor.get("imported", ()))
    unique = {}
    metrics = dict(run.fetch_metrics or {})
    metrics["found"] = metrics.get("found", 0) + len(candidates)
    for item in candidates:
        try:
            url = canonical_url(item.url, source.allowed_hosts)
        except ValueError:
            metrics["rejected"] = metrics.get("rejected", 0) + 1
            continue
        unique.setdefault(url, item)
    metrics["duplicates"] = metrics.get("duplicates", 0) + len(candidates) - len(unique) - (
        metrics.get("rejected", 0) - (run.fetch_metrics or {}).get("rejected", 0))
    seen_in_run = set(session.scalars(select(Discovery.url).where(Discovery.run_id == run.id)))
    for url, item in unique.items():
        if url in seen_in_run:
            metrics["duplicates"] += 1
            continue
        previous = _lookup(session, url)
        if first:
            if url in imported:
                continue
            if len(imported) >= FIRST_IMPORT_LIMIT or not previous and _before(item, now - FIRST_IMPORT_AGE):
                continue
            imported.add(url)
        elif not previous and _before(item, utc(source.collection_initialized_at) - STALE_ON_DISCOVERY):
            metrics["history_skipped"] = metrics.get("history_skipped", 0) + 1
            continue

        # A canonical URL owned by another channel keeps its original provenance.
        if previous and previous.source_id != source.id:
            session.add(Discovery(run_id=run.id, source_id=source.id, url=url,
                                  material_id=previous.id, outcome="duplicate"))
            metrics["duplicates"] += 1
            continue
        listing = _pack(item)
        listing_hash = hashlib.sha256(json.dumps(listing, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        changed = bool(previous and previous.listing_hash and previous.listing_hash != listing_hash)
        merged = _merge(item, previous, listing=True)
        material = previous
        outcome = "discovered"
        if merged.title.strip():
            material, outcome = store_candidate(session, source, merged, now)
            material.listing_hash = listing_hash
            if outcome == "new" and first:
                material.backfill_reason = "first-import"
            elif outcome == "new" and material.timeline_kind == "historical":
                material.backfill_reason = "stale-on-discovery"
        incomplete = not material or not material.source_body or not (
            material.published_at or material.published_date)
        needs_detail = incomplete or changed
        if material and (not incomplete or not needs_detail):
            material.collection_state = "complete"
        session.add(Discovery(run_id=run.id, source_id=source.id, url=url,
                              material_id=material.id if material else None, outcome=outcome))
        counter = {"new": "added", "revised": "revised", "duplicate": "duplicates"}.get(outcome, "metadata_pending")
        metrics[counter] = metrics.get(counter, 0) + 1
        if needs_detail and (not material or material.collection_state != "unconfirmed" or changed):
            identity = f"{source.slug}:{hashlib.sha256(url.encode()).hexdigest()}:{listing_hash}"
            existing = session.scalar(select(WorkItem).where(WorkItem.kind == "extract", WorkItem.identity == identity))
            if existing is None:
                enqueue(session, "extract", identity, {
                    "slug": source.slug, "url": url, "candidate": listing, "listing_hash": listing_hash,
                    "material_id": material.id if material else None,
                    "revision": material.revision if material else None,
                    "run_id": run.id, "discovered_at": now.isoformat(), "first_import": first,
                    "historical": bool(material and material.timeline_kind == "historical" or
                                       _before(item, now - STALE_ON_DISCOVERY)),
                }, now)
                if material and incomplete:
                    material.collection_state = "pending"
                metrics["detail_queued"] = metrics.get("detail_queued", 0) + 1
    if first:
        cursor["imported"] = sorted(imported)
    run.fetch_metrics = metrics
    run.candidate_count += len(unique)


def detail_is_current(session, source, payload):
    if not source or not source.enabled:
        return False
    previous = _lookup(session, payload["url"])
    if not previous:
        newer = session.scalar(select(WorkItem.id).where(
            WorkItem.kind == "extract", WorkItem.payload["slug"].as_string() == source.slug,
            WorkItem.payload["url"].as_string() == payload["url"],
            WorkItem.payload["discovered_at"].as_string() > payload["discovered_at"],
        ).limit(1))
        return payload["material_id"] is None and newer is None
    return (previous.id == payload["material_id"] and previous.source_id == source.id and
            previous.revision == payload["revision"] and previous.listing_hash == payload["listing_hash"] and
            not previous.withdrawn)


def apply_detail(session, source, payload, candidate, now):
    if not detail_is_current(session, source, payload):
        return None
    previous = _lookup(session, payload["url"])
    if candidate is None:
        if previous and previous.collection_state == "pending":
            previous.collection_state = "unconfirmed"
        return previous
    if canonical_url(candidate.url, source.allowed_hosts) != payload["url"]:
        raise ValueError("detail_identity_changed")
    merged = _merge(candidate, previous, listing=False)
    if not merged.title.strip():
        raise ValueError("title_missing")
    discovered = datetime.fromisoformat(payload["discovered_at"])
    item, outcome = store_candidate(session, source, merged, now if previous else discovered)
    if outcome == "new" and payload["first_import"]:
        item.backfill_reason = "first-import"
    elif outcome == "new" and item.timeline_kind == "historical":
        item.backfill_reason = "stale-on-discovery"
    item.fetched_at = now
    item.listing_hash = payload["listing_hash"]
    item.collection_state = "complete" if item.source_body else "unconfirmed"
    for discovery in session.scalars(select(Discovery).where(
            Discovery.run_id == payload["run_id"], Discovery.url == payload["url"])):
        if discovery.material_id is None:
            discovery.material_id = item.id
            discovery.outcome = outcome
    return item


def schedule_due_sources(session, now, slugs=None):
    due = select(Source).where(Source.enabled.is_(True), Source.slug.in_(slugs or ()),
                                or_(Source.next_fetch_at.is_(None), Source.next_fetch_at <= now))
    for source in session.scalars(due.order_by(Source.next_fetch_at, Source.slug).limit(40)):
        active = session.scalar(select(WorkItem.id).where(
            WorkItem.kind == "collect", WorkItem.status.in_(("pending", "running")),
            WorkItem.payload["slug"].as_string() == source.slug,
        ).limit(1))
        if not active:
            enqueue(session, "collect", f"{source.slug}:listing:{now.isoformat()}", {"slug": source.slug}, now)
        source.next_fetch_at = now + timedelta(minutes=10)


def schedule_after_fetch(source, now, *, success):
    if success:
        source.collection_failures = 0
        delay = source.interval_minutes
    else:
        delay = min(source.interval_minutes * (source.collection_failures + 2), 360)
        source.collection_failures += 1
    source.next_fetch_at = now + timedelta(minutes=delay)


def adapt_intervals(session, now, slugs):
    # AIHOT adapts once a day at 04:20 in the site's Asia/Shanghai timezone.
    local = now.astimezone(timezone(timedelta(hours=8)))
    if (local.hour, local.minute) < (4, 20):
        return 0
    identity = local.date().isoformat()
    if session.scalar(select(WorkItem.id).where(WorkItem.kind == "source_adapt",
                                               WorkItem.identity == identity)):
        return 0
    task = enqueue(session, "source_adapt", identity, {}, now)
    task.status = "done"
    counts = dict(session.execute(select(Material.source_id, func.count()).where(
        Material.first_seen_at >= now - timedelta(days=7), Material.backfill_reason.is_(None),
        Material.timeline_kind == "fresh",
    ).group_by(Material.source_id)).all())
    updated = 0
    for source in session.scalars(select(Source).where(Source.enabled.is_(True), Source.slug.in_(slugs))):
        maximum = 180 if source.participation_mode == "hot_signal" else 60
        per_day = counts.get(source.id, 0) / 7
        target = maximum if per_day <= .15 else int(min(maximum, max(15, 1440 / (per_day * 3))) + .5)
        if source.interval_minutes != target:
            source.interval_minutes = target
            updated += 1
    task.result = {"updated": updated}
    return updated
