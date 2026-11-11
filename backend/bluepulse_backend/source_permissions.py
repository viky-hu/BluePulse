"""Apply the project's versioned publication policy to the built-in sources."""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .admin_models import AdminAudit
from .admin_operations import reproject_source
from .db import make_engine
from .models import Material, now_utc
from .publication import refresh_source_publication, translation_needed
from .source_collection import SOURCES, ensure_source
from .work_queue import enqueue_translation


AIHOT_TIER_THRESHOLDS = {"T1": 60, "T1_5": 65, "T2": 76}
LOCAL_LIVE_PROFILE = "local-live-v1"
LOCAL_LIVE_FULL_TEXT_PROFILE = "local-live-full-text-v2"
LOCAL_LIVE_FULL_TEXT_SOURCES = frozenset({
    "govuk", "ccgp-policing-tech", "nist-public-safety", "nist-forensic-science",
    "nist-information-technology", "nist-standards", "htx-news", "police-science",
    "npcc", "jiangsu-police", "police-digital-service", "biometric-update-law-enforcement",
    "statescoop-law-enforcement-tech", "europol-news", "spf-police-life",
})


def initialize_local_live(session: Session, sources) -> None:
    """Apply each approved policy once in the caller's write transaction."""
    applied_profiles = set(session.scalars(select(AdminAudit.subject).where(
        AdminAudit.action == "source.bootstrap",
        AdminAudit.subject.in_((LOCAL_LIVE_PROFILE, LOCAL_LIVE_FULL_TEXT_PROFILE)),
    )))
    if {LOCAL_LIVE_PROFILE, LOCAL_LIVE_FULL_TEXT_PROFILE} <= applied_profiles:
        return
    changed_by_admin = set()
    for entry in session.scalars(select(AdminAudit).where(AdminAudit.action == "source.update")):
        changes = entry.changes or {}
        before, after = changes.get("before", {}), changes.get("after", {})
        changed_by_admin.update((entry.subject, field) for field in after if before.get(field) != after[field])
        if after.keys() == {"full_text_allowed"}:
            # A dedicated PATCH can explicitly keep the existing value. Legacy bulk forms send all flags.
            changed_by_admin.add((entry.subject, "full_text_allowed"))

    if LOCAL_LIVE_PROFILE not in applied_profiles:
        _initialize_excerpts(session, sources, changed_by_admin)
    if LOCAL_LIVE_FULL_TEXT_PROFILE not in applied_profiles:
        _initialize_full_text(session, sources, changed_by_admin)


def _initialize_excerpts(session: Session, sources, changed_by_admin) -> None:
    applied = {}
    for source in sources:
        subject = f"source:{source.id}"
        if source.tier is None and (subject, "tier") not in changed_by_admin:
            source.tier = SOURCES[source.slug].tier
        threshold = AIHOT_TIER_THRESHOLDS.get(source.tier)
        threshold_changed = (threshold is not None and source.selection_threshold is None and
                             (subject, "selection_threshold") not in changed_by_admin)
        if (subject, "excerpt_allowed") not in changed_by_admin:
            source.excerpt_allowed = True
        if threshold_changed:
            source.selection_threshold = threshold
        released = reproject_source(session, source, threshold_changed=threshold_changed, fresh_only=True)
        applied[source.slug] = {"excerpt_allowed": source.excerpt_allowed, "tier": source.tier,
                                "selection_threshold": source.selection_threshold, "released": released}
    session.add(AdminAudit(actor="system:launcher", action="source.bootstrap", subject=LOCAL_LIVE_PROFILE,
                           reason="Approved local publication defaults and AIHOT tier thresholds", changes=applied))


def _initialize_full_text(session: Session, sources, changed_by_admin) -> None:
    applied = {}
    source_ids = []
    for source in sources:
        if (source.slug not in LOCAL_LIVE_FULL_TEXT_SOURCES or
                (f"source:{source.id}", "full_text_allowed") in changed_by_admin):
            continue
        source_ids.append(source.id)
        if not source.full_text_allowed:
            source.full_text_allowed = True
            applied[source.slug] = {"before": False, "after": True}

    now = now_utc()
    for item in session.scalars(select(Material).where(
        Material.source_id.in_(source_ids),
        Material.selected_at.is_not(None),
        Material.withdrawn.is_(False),
    )):
        if translation_needed(item, at=now):
            enqueue_translation(session, item, now)
    session.add(AdminAudit(actor="system:launcher", action="source.bootstrap",
                           subject=LOCAL_LIVE_FULL_TEXT_PROFILE,
                           reason="Restore approved on-site full text for built-in sources", changes=applied))


def allow_excerpts_for_active_sources(session: Session) -> dict:
    changed = []
    for spec in SOURCES.values():
        source = ensure_source(session, spec)
        if not source.excerpt_allowed:
            source.excerpt_allowed = True
            changed.append(spec.slug)
    session.commit()
    projection = {}
    for spec in SOURCES.values():
        source = ensure_source(session, spec)
        projection[spec.slug] = refresh_source_publication(session, source.id)
    return {"active_sources": len(SOURCES), "excerpt_enabled": changed,
            "full_text_permissions_changed": 0, "publication_projection": projection}


def allow_full_text_for_active_sources(session: Session) -> dict:
    """Explicit user policy: permit on-site full body reading for the 15 active sources."""
    excerpt_changed = []
    full_text_changed = []
    for spec in SOURCES.values():
        source = ensure_source(session, spec)
        if not source.excerpt_allowed:
            source.excerpt_allowed = True
            excerpt_changed.append(spec.slug)
        if not source.full_text_allowed:
            source.full_text_allowed = True
            full_text_changed.append(spec.slug)
    session.commit()
    projection = {}
    for spec in SOURCES.values():
        source = ensure_source(session, spec)
        projection[spec.slug] = refresh_source_publication(session, source.id)
    return {"active_sources": len(SOURCES), "excerpt_enabled": excerpt_changed,
            "full_text_enabled": full_text_changed,
            "publication_projection": projection}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply explicit excerpt permission to all 15 active sources")
    parser.add_argument("--database-url", required=True, help="already migrated target database")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-full-text", action="store_true",
                        help="also expose captured full text in public article details")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required to change source permissions")
    engine = make_engine(args.database_url)
    try:
        with Session(engine) as session:
            result = (allow_full_text_for_active_sources(session) if args.allow_full_text else
                      allow_excerpts_for_active_sources(session))
            print(json.dumps(result, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
