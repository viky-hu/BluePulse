"""Explicitly apply the project's excerpt publication decision to active sources."""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .admin_models import AdminAudit
from .admin_operations import reproject_source
from .db import make_engine
from .publication import refresh_source_publication
from .source_collection import SOURCES, ensure_source


AIHOT_TIER_THRESHOLDS = {"T1": 60, "T1_5": 65, "T2": 76}
LOCAL_LIVE_PROFILE = "local-live-v1"


def initialize_local_live(session: Session, sources) -> None:
    """Apply the approved local publication defaults once in the caller's write transaction."""
    if session.scalar(select(AdminAudit.id).where(
            AdminAudit.action == "source.bootstrap", AdminAudit.subject == LOCAL_LIVE_PROFILE).limit(1)):
        return
    changed_by_admin = set()
    for entry in session.scalars(select(AdminAudit).where(AdminAudit.action == "source.update")):
        changes = entry.changes or {}
        before, after = changes.get("before", {}), changes.get("after", {})
        changed_by_admin.update((entry.subject, field) for field in after if before.get(field) != after[field])

    applied = {}
    for source in sources:
        subject = f"source:{source.id}"
        threshold = AIHOT_TIER_THRESHOLDS.get(source.tier)
        threshold_changed = (threshold is not None and source.selection_threshold is None and
                             (subject, "selection_threshold") not in changed_by_admin)
        if (subject, "excerpt_allowed") not in changed_by_admin:
            source.excerpt_allowed = True
        if threshold_changed:
            source.selection_threshold = threshold
        released = reproject_source(session, source, threshold_changed=threshold_changed, fresh_only=True)
        applied[source.slug] = {"excerpt_allowed": source.excerpt_allowed,
                                "selection_threshold": source.selection_threshold, "released": released}
    session.add(AdminAudit(actor="system:launcher", action="source.bootstrap", subject=LOCAL_LIVE_PROFILE,
                           reason="Approved local publication defaults and AIHOT tier thresholds", changes=applied))


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
